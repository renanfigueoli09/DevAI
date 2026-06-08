"""
DevAI Auto-Study v5 — Loop inteligente com diário de estudo.

Não repete o que já foi estudado. Prioriza:
  1. Tópicos nunca estudados
  2. Tópicos com baixa pontuação na validação
  3. Tópicos descobertos autonomamente (novos)
  4. Tópicos estudados há mais de REVISIT_HOURS horas

Fluxo por ciclo:
  1. Lê o diário (study_journal.json) — o que já foi feito
  2. Calcula prioridade de cada tópico
  3. Estuda apenas o que é necessário
  4. Descobre novos tópicos e os adiciona à fila
  5. Valida e atualiza o diário
  6. Salva e commita
"""

import argparse, json, re, sys, time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Score mínimo para considerar um tópico "aprovado" no knowledge check
SCORE_THRESHOLD = 0.70

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()

JOURNAL_FILE      = DEVAI_DIR / "training" / "study_journal.json"
DISCOVERED_FILE   = DEVAI_DIR / "training" / "discovered_topics.json"

REVISIT_HOURS     = 48    # só revisita após 48h
INTENSIVE_RESULTS = 6     # resultados por query em modo intensivo
NORMAL_RESULTS    = 4


# ─── Diário de estudo ─────────────────────────────────────────────────────────

@dataclass
class TopicEntry:
    topic:        str
    last_studied: float = 0.0      # timestamp
    times_studied: int  = 0
    last_score:   float = -1.0     # -1 = não validado
    items_saved:  int   = 0
    source:       str   = "curriculum"  # curriculum | discovered

def load_journal() -> dict[str, TopicEntry]:
    if JOURNAL_FILE.exists():
        try:
            raw = json.loads(JOURNAL_FILE.read_text())
            return {k: TopicEntry(**v) for k, v in raw.items()}
        except Exception:
            pass
    return {}

def save_journal(journal: dict[str, TopicEntry]):
    JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_FILE.write_text(
        json.dumps({k: asdict(v) for k, v in journal.items()}, indent=2),
        encoding="utf-8"
    )

def load_discovered() -> dict[str, list]:
    if DISCOVERED_FILE.exists():
        try:
            return json.loads(DISCOVERED_FILE.read_text())
        except Exception:
            pass
    return {}

def save_discovered(topics: dict):
    DISCOVERED_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERED_FILE.write_text(json.dumps(topics, indent=2, ensure_ascii=False))


# ─── Prioridade de estudo ────────────────────────────────────────────────────

def topic_priority(entry: Optional[TopicEntry], now: float) -> float:
    """
    Calcula a prioridade de estudo de um tópico.
    Maior = mais urgente.

    Critérios:
      +100  nunca estudado
      +80   score de validação baixo (<50%)
      +60   score médio (50-70%)
      +40   não estudado há muito tempo (>REVISIT_HOURS)
      +0    estudado recentemente com bom score → pula
    """
    if entry is None or entry.times_studied == 0:
        return 100.0  # nunca estudado — máxima prioridade

    hours_ago = (now - entry.last_studied) / 3600

    if entry.last_score >= 0:  # foi validado
        if entry.last_score < 0.5:   return 80.0  # muito fraco
        if entry.last_score < 0.7:   return 60.0  # médio
        if hours_ago > REVISIT_HOURS * 2:          return 20.0  # bom mas antigo
        return 0.0  # bem estudado e recente → pula

    # Nunca validado, mas estudado
    if hours_ago > REVISIT_HOURS:   return 40.0
    if hours_ago > REVISIT_HOURS/2: return 15.0
    return 0.0  # estudado recentemente


def should_study(entry: Optional[TopicEntry], now: float, force: bool = False) -> bool:
    return force or topic_priority(entry, now) > 0


# ─── Curriculum completo ─────────────────────────────────────────────────────

SEARCH_CURRICULUM: dict[str, list] = {
  # NestJS × cada banco
  "nestjs+mongodb":       ["NestJS Mongoose MongooseModule @Schema @Prop HydratedDocument 2025","NestJS Mongoose findById findByIdAndUpdate findByIdAndDelete 2025","NestJS Mongoose populate transactions indexes 2025","NestJS Mongoose TypeScript strict mode ! ? 2025"],
  "nestjs+postgres":      ["NestJS TypeORM forRootAsync @Entity @Column 2025","NestJS TypeORM @InjectRepository Repository CRUD 2025","NestJS TypeORM relations migration QueryBuilder 2025"],
  "nestjs+mysql":         ["NestJS TypeORM MySQL mysql2 entity 2025","NestJS TypeORM MySQL relations indexes 2025"],
  "nestjs+redis":         ["NestJS @nestjs/cache-manager CacheModule Redis 2025","NestJS @nestjs/bull BullModule queue processor 2025","NestJS ioredis sentinel cluster 2025"],
  "nestjs+elasticsearch": ["NestJS @elastic/elasticsearch index search 2025","NestJS Elasticsearch mapping aggregation 2025"],
  "nestjs+cassandra":     ["NestJS cassandra-driver keyspace CQL 2025"],
  # NestJS × microserviços
  "nestjs+kafka":         ["NestJS Kafka ClientKafka emit @EventPattern 2025","NestJS Kafka error retry dead letter queue 2025","NestJS Kafka transaction idempotent 2025"],
  "nestjs+rabbitmq":      ["NestJS RabbitMQ Transport.RMQ ClientProxy 2025","NestJS RabbitMQ dead letter exchange DLX 2025"],
  "nestjs+grpc":          ["NestJS gRPC Transport.GRPC proto @GrpcMethod 2025","NestJS gRPC client stub injection streaming 2025"],
  "nestjs+graphql":       ["NestJS GraphQL ApolloDriver @ObjectType @Resolver 2025","NestJS GraphQL @Subscription dataloader N+1 2025"],
  "nestjs+websocket":     ["NestJS @WebSocketGateway @SubscribeMessage WsAdapter JWT 2025"],
  "nestjs+auth":          ["NestJS JWT Passport JwtStrategy LocalStrategy 2025","NestJS @UseGuards JwtAuthGuard bcryptjs refresh token 2025","NestJS RBAC @Roles @SetMetadata Reflector 2025"],
  "nestjs+core":          ["NestJS ValidationPipe ConfigModule Swagger lifecycle 2025","NestJS exception filter interceptor guard @Cron 2025","NestJS circular dependency forwardRef custom decorator 2025"],
  # Spring Boot × bancos e microserviços
  "spring+mongodb":       ["Spring Data MongoDB @Document MongoRepository aggregation 2025","Spring Boot MongoDB ReactiveMongoRepository WebFlux 2025"],
  "spring+postgres":      ["Spring Boot JPA @Entity JpaRepository @Query migration 2025","Spring Boot Flyway HikariCP @Transactional 2025"],
  "spring+mysql":         ["Spring Boot MySQL JPA Pageable migration 2025"],
  "spring+redis":         ["Spring Boot @Cacheable Redis Lettuce session 2025"],
  "spring+elasticsearch": ["Spring Data Elasticsearch @Document search 2025"],
  "spring+kafka":         ["Spring Boot KafkaTemplate @KafkaListener error handler 2025"],
  "spring+rabbitmq":      ["Spring Boot RabbitMQ @RabbitListener DLX 2025"],
  "spring+grpc":          ["Spring Boot gRPC grpc-spring-boot-starter @GrpcService 2025"],
  "spring+auth":          ["Spring Security 6 JWT SecurityFilterChain @PreAuthorize 2025"],
  "spring+core":          ["Spring Boot @Valid @ControllerAdvice Actuator @Async @Scheduled 2025"],
  # FastAPI × bancos
  "fastapi+mongodb":      ["FastAPI Motor AsyncIOMotorClient Beanie async CRUD 2025"],
  "fastapi+postgres":     ["FastAPI SQLAlchemy 2.0 async mapped_column Alembic 2025"],
  "fastapi+redis":        ["FastAPI redis-py aioredis cache session rate limit 2025"],
  "fastapi+kafka":        ["FastAPI aiokafka producer consumer background 2025"],
  "fastapi+auth":         ["FastAPI OAuth2PasswordBearer JWT passlib refresh token 2025"],
  "fastapi+core":         ["FastAPI Pydantic v2 Depends background WebSocket testing 2025"],
  "django+core":          ["Django REST Framework ViewSet JWT Celery channels 2025"],
  # ASP.NET Core × bancos
  "dotnet+mongodb":       ["ASP.NET Core MongoDB.Driver IMongoCollection BSON 2025"],
  "dotnet+postgres":      ["ASP.NET Core EF Core Npgsql migrations DbContext 2025"],
  "dotnet+redis":         ["ASP.NET Core StackExchange.Redis IDistributedCache SignalR 2025"],
  "dotnet+kafka":         ["ASP.NET Core Confluent.Kafka MassTransit 2025"],
  "dotnet+auth":          ["ASP.NET Core JWT AddAuthentication Identity OAuth2 2025"],
  "dotnet+core":          ["ASP.NET Core minimal API DI middleware Swagger health 2025"],
  # Frontend
  "nextjs+core":          ["Next.js 15 App Router server actions middleware ISR 2025"],
  "nextjs+mongodb":       ["Next.js MongoDB Mongoose singleton connection 2025"],
  "nextjs+auth":          ["Next.js NextAuth.js v5 session JWT 2025"],
  "react+core":           ["React 19 hooks TanStack Query Zustand TypeScript 2025"],
  "angular+core":         ["Angular 19 standalone signals HttpClient guards 2025"],
  # Bancos avançados
  "mongodb+advanced":     ["MongoDB aggregation transactions Atlas indexing schema patterns 2025"],
  "postgres+advanced":    ["PostgreSQL JSONB partitioning full text search pg_cron 2025"],
  "redis+advanced":       ["Redis Streams Sentinel Cluster Lua scripts pub/sub 2025"],
  "elasticsearch+setup":  ["Elasticsearch mapping query DSL aggregation Node.js 2025"],
  # Microservices patterns
  "microservices+patterns":["Saga CQRS Event Sourcing Circuit Breaker API Gateway 2025","Outbox pattern DDD bounded context service mesh 2025"],
  "rabbitmq+advanced":    ["RabbitMQ exchanges routing DLX priority queue 2025"],
  # Infra
  "docker+patterns":      ["docker-compose healthcheck depends_on multi-stage security 2025"],
  "docker+stacks":        ["docker-compose NestJS Spring FastAPI .NET MongoDB Redis Kafka 2025"],
  "kubernetes+setup":     ["Kubernetes deployment service ingress HPA Helm secrets 2025"],
  # CI/CD
  "github-actions+ci":    ["GitHub Actions NestJS Spring Docker cache matrix 2025"],
  "gitlab-ci":            ["GitLab CI stages artifacts cache Docker registry 2025"],
  "azure-devops":         ["Azure DevOps pipelines task Docker deployment 2025"],
  "bitbucket-pipelines":  ["Bitbucket Pipelines branches Docker services 2025"],
  "circleci":             ["CircleCI orbs jobs workflows Docker 2025"],
  # NLP e erros
  "nlp+patterns":         ["NestJS TypeScript entity extraction from description 2025","common mistakes LLM code generation NestJS patterns 2025"],
  "common+errors":        ["NestJS TS2307 TS2339 TS2551 TypeScript errors fix 2025","Mongoose findOneBy does not exist findById fix 2025","NestJS module missing app.module cannot find module 2025","PartialType @nestjs/mapped-types not @nestjs/common 2025"],

  # ── Metodologia e Arquitetura ─────────────────────────────────────────────
  "clean-architecture":   ["Clean Architecture backend NestJS Spring FastAPI 2025","SOLID principles TypeScript NestJS examples 2025","DRY YAGNI KISS principles code examples 2025","dependency injection inversion of control 2025","separation of concerns layered architecture 2025"],
  "api-design":           ["REST API best practices versioning pagination 2025","API design naming conventions HTTP status codes 2025","OpenAPI Swagger documentation best practices 2025","API authentication strategies JWT OAuth comparison 2025","rate limiting throttling API gateway patterns 2025"],
  "database-design":      ["when to use MongoDB vs PostgreSQL decision guide 2025","database normalization denormalization trade-offs 2025","NoSQL vs SQL use cases pros cons 2025","database indexing strategies performance 2025","data modeling patterns embedded vs referenced MongoDB 2025","schema design decisions relational database 2025"],
  "security-patterns":    ["API security OWASP top 10 backend 2025","SQL injection XSS CSRF prevention NestJS Spring 2025","JWT security best practices expiry rotation 2025","input validation sanitization backend patterns 2025","secrets management environment variables 2025","HTTPS TLS certificate backend configuration 2025"],
  "testing-patterns":     ["unit testing NestJS Jest mock service 2025","integration testing NestJS supertest e2e 2025","unit testing Spring Boot JUnit Mockito 2025","FastAPI pytest async testing fixtures 2025","test driven development TDD examples 2025","testing MongoDB in-memory mongoms jest 2025"],
  "performance-patterns": ["NestJS performance optimization caching 2025","database query optimization N+1 problem solution 2025","async concurrency patterns Node.js performance 2025","pagination cursor-based offset comparison 2025","lazy loading eager loading strategy 2025","connection pooling database performance 2025"],
  "error-handling":       ["error handling strategy NestJS global filter 2025","exception hierarchy domain errors application errors 2025","error logging structured Winston Pino 2025","retry pattern exponential backoff 2025","circuit breaker pattern implementation 2025","validation error response format RFC 7807 2025"],
  "code-quality":         ["TypeScript strict mode best practices 2025","code review checklist backend developer 2025","naming conventions functions classes interfaces 2025","anti-patterns to avoid backend development 2025","refactoring patterns legacy code 2025","technical debt identification resolution 2025"],
  "devops-practices":     ["12 factor app methodology backend 2025","containerization best practices Docker 2025","CI/CD pipeline best practices testing deployment 2025","blue green deployment canary release 2025","environment configuration staging production 2025","observability logging metrics tracing 2025"],
  "microservices-design": ["microservices decomposition strategy 2025","service communication patterns sync async 2025","data consistency distributed systems 2025","API gateway pattern implementation 2025","service discovery load balancing 2025","idempotency distributed systems patterns 2025"],
  "anti-patterns":        ["common NestJS mistakes anti-patterns 2025","common Spring Boot mistakes beginners 2025","fat controller anti-pattern solution 2025","god object anti-pattern refactoring 2025","premature optimization anti-pattern 2025","over-engineering simple solutions anti-pattern 2025"],
}

TOPIC_GROUPS = {
  "quick":          ["nestjs+mongodb","nestjs+core","docker+patterns","common+errors","nlp+patterns"],
  "nestjs":         [t for t in SEARCH_CURRICULUM if t.startswith("nestjs+")],
  "spring":         [t for t in SEARCH_CURRICULUM if t.startswith("spring+")],
  "python":         [t for t in SEARCH_CURRICULUM if t.startswith(("fastapi+","django+"))],
  "dotnet":         [t for t in SEARCH_CURRICULUM if t.startswith("dotnet+")],
  "frontend":       [t for t in SEARCH_CURRICULUM if t.startswith(("nextjs+","react+","angular+"))],
  "databases":      [t for t in SEARCH_CURRICULUM if any(t.startswith(x) for x in ("mongodb+","postgres+","redis+","elasticsearch+"))],
  "microservices":  [t for t in SEARCH_CURRICULUM if any(t.startswith(x) for x in ("nestjs+kafka","nestjs+rabbitmq","nestjs+grpc","spring+kafka","spring+rabbitmq","fastapi+kafka","dotnet+kafka","microservices+","rabbitmq+"))],
  "infra":          [t for t in SEARCH_CURRICULUM if any(t.startswith(x) for x in ("docker+","kubernetes+","github-actions+","gitlab-ci","azure-devops","bitbucket","circleci"))],
  "methodology":    ["clean-architecture","api-design","database-design","security-patterns",
                     "testing-patterns","performance-patterns","error-handling",
                     "code-quality","devops-practices","microservices-design","anti-patterns"],
  "all":            list(SEARCH_CURRICULUM.keys()),
}

DISCOVERY_PROMPT = """Training curriculum already covers: {topics}

Suggest 5 NEW specific technical topics NOT yet covered that would improve code generation.
Focus on: specific stack+database combos, error patterns, security, testing, performance.

Return ONLY JSON array:
[{{"topic":"nestjs+prisma","searches":["NestJS Prisma ORM CRUD 2025","NestJS Prisma migrations 2025"]}}]"""

BASE_PATTERNS_COUNT = 42  # patterns in study.py


# ─── Core functions ──────────────────────────────────────────────────────────

def load_llm():
    from tools.llm_client import OllamaClient
    from config import MODEL_CODE
    llm = OllamaClient()
    llm.ensure_model(MODEL_CODE)
    return llm, MODEL_CODE


def study_topic(key: str, searches: list, llm, model: str, intensive: bool = False) -> int:
    from tools.vector_store import save, get as vs_get
    from tools.research_agent import _summarize
    from tools.web_research import web_search
    saved = 0
    for q in searches:
        k = f"search:{key}:{re.sub(r'\\W+','_',q[:30].lower())}"
        # Skip if cached and not intensive
        if not intensive and vs_get(k):
            continue
        console.print(f"  [dim]🔍 {q[:72]}[/dim]")
        try:
            results = web_search(q, max_results=INTENSIVE_RESULTS if intensive else NORMAL_RESULTS)
            if not results: continue
            summary = _summarize(q, results, llm, model)
            if not summary: continue
            save(k, summary, topic=re.sub(r"[^\w]","_",key), source="web_search"); saved += 1
            if intensive:
                ex = web_search(f"code example {q}", max_results=3)
                if ex:
                    ex_s = _summarize(f"example: {q}", ex, llm, model)
                    if ex_s: save(f"{k}_ex", ex_s, topic=re.sub(r"[^\w]","_",key), source="code_example"); saved += 1
            time.sleep(2 if intensive else 1)
        except Exception as e:
            console.print(f"  [dim]⚠ {e}[/dim]")
    return saved


def save_code_patterns() -> int:
    """Saves the base code patterns (always runs, idempotent)."""
    from tools.vector_store import save
    # Import patterns from the old v4 patterns list condensed
    PATTERNS = [
      {"key":"pattern:nestjs+mongodb:schema","topic":"nestjs-mongodb","content":"""// book.schema.ts — CORRECT Mongoose NestJS pattern
import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';  // HydratedDocument, NOT Document

export type BookDocument = HydratedDocument<Book>;  // NOT Book & Document

@Schema({ timestamps: true })
export class Book {  // MUST have export keyword
  @Prop({ required: true }) title!: string;   // required → ! (non-null assertion)
  @Prop({ required: true }) author!: string;  // required → !
  @Prop() description?: string;               // optional → ?
  @Prop({ default: true }) isActive?: boolean; // optional with default → ?
}
export const BookSchema = SchemaFactory.createForClass(Book);
// RULES: 1) export class 2) HydratedDocument not Document 3) required=! optional=?"""},
      {"key":"pattern:nestjs+mongodb:service","topic":"nestjs-mongodb","content":"// service.ts: @InjectModel(Book.name) private model: Model<BookDocument>. findAll(){return this.model.find().exec()} findOne(id){return this.model.findById(id).exec()} create(dto){return new this.model(dto).save()} update(id,dto){return this.model.findByIdAndUpdate(id,{$set:dto},{new:true}).exec()} remove(id){return this.model.findByIdAndDelete(id).exec()}"},
      {"key":"pattern:nestjs+mongodb:module","topic":"nestjs-mongodb","content":"// module.ts: @Module({imports:[MongooseModule.forFeature([{name:Book.name,schema:BookSchema}])],providers:[BookService],controllers:[BookController],exports:[BookService]}) export class BookModule {}"},
      {"key":"pattern:nestjs+mongodb:app-module","topic":"nestjs","content":"// app.module.ts MongoDB: MongooseModule.forRoot(process.env.MONGODB_URI||'mongodb://localhost:27017/app'). ONLY add modules that exist. NOT JwtModule/Redis/Kafka unless requested."},
      {"key":"pattern:nestjs+postgres:entity","topic":"nestjs-typeorm","content":"// entity.ts: @Entity('books') class Book { @PrimaryGeneratedColumn('uuid') id:string; @Column({nullable:false}) title:string; @Column({nullable:true}) description?:string; @CreateDateColumn() createdAt:Date; }"},
      {"key":"pattern:nestjs+postgres:service","topic":"nestjs-typeorm","content":"// service.ts TypeORM: @InjectRepository(Book) private repo:Repository<Book>. findAll(){return this.repo.find()} findOne(id){return this.repo.findOne({where:{id}})} create(dto){return this.repo.save(this.repo.create(dto as any))} update(id,dto){await this.repo.update(id,dto as any);return this.findOne(id)} remove(id){return this.repo.delete(id)}"},
      {"key":"pattern:nestjs+postgres:app-module","topic":"nestjs","content":"// app.module.ts PostgreSQL: TypeOrmModule.forRootAsync({useFactory:(c:ConfigService)=>({type:'postgres',host:c.get('DB_HOST'),port:+c.get('DB_PORT',5432),database:c.get('DB_NAME'),username:c.get('DB_USER'),password:c.get('DB_PASS'),entities:[__dirname+'/**/*.entity.js'],synchronize:c.get('NODE_ENV')!=='production'}),inject:[ConfigService]})"},
      {"key":"pattern:nestjs:dto","topic":"nestjs","content":"// dto.ts: import {PartialType} from '@nestjs/mapped-types' (NEVER @nestjs/common). export class UpdateBookDto extends PartialType(CreateBookDto) {}"},
      {"key":"pattern:nestjs:main","topic":"nestjs","content":"// main.ts: ValidationPipe({whitelist:true,transform:true}). Swagger: DocumentBuilder().setTitle().setVersion().addBearerAuth().build(). SwaggerModule.setup('swagger',app,doc)."},
      {"key":"pattern:nestjs-auth:jwt","topic":"nestjs-auth","content":"// jwt.strategy.ts: extends PassportStrategy(Strategy). super({jwtFromRequest:ExtractJwt.fromAuthHeaderAsBearerToken(),secretOrKey:config.get('JWT_SECRET')}). validate(p:{sub,email}){return {id:p.sub,email:p.email}}. jwt.guard.ts: extends AuthGuard('jwt'){}"},
      {"key":"pattern:nestjs+kafka:setup","topic":"nestjs-kafka","content":"// Kafka: app.connectMicroservice({transport:Transport.KAFKA,options:{client:{brokers:[KAFKA_BROKER]},consumer:{groupId:'app-group',allowAutoTopicCreation:true}}}). Producer: ClientKafka.emit(topic,data). Consumer: @EventPattern('topic') handle(@Payload() data){}"},
      {"key":"pattern:spring+mongodb:document","topic":"spring-boot-mongodb","content":"// @Document(collection='books') @Data class Book { @Id String id; @NotBlank String title; @CreatedDate LocalDateTime createdAt; }. Repository: extends MongoRepository<Book,String>{}"},
      {"key":"pattern:spring+postgres:entity","topic":"spring-boot-postgres","content":"// @Entity @Table(name='books') @Data class Book { @Id @GeneratedValue(strategy=UUID) String id; @Column(nullable=false) String title; @CreationTimestamp LocalDateTime createdAt; }. Repository: extends JpaRepository<Book,String>{}"},
      {"key":"pattern:fastapi+mongodb:crud","topic":"python-fastapi","content":"// FastAPI MongoDB: db=AsyncIOMotorClient(MONGODB_URI).myapp. @app.get('/books') async def list(): return [serialize(b) async for b in db.books.find()]. @app.post('/books',status_code=201) async def create(b:BookCreate): r=await db.books.insert_one(b.model_dump()); return {'id':str(r.inserted_id)}"},
      {"key":"pattern:fastapi+postgres:sqlalchemy","topic":"python-fastapi","content":"// FastAPI PostgreSQL: engine=create_async_engine(DATABASE_URL). class Book(Base): __tablename__='books'; id:Mapped[int]=mapped_column(primary_key=True); title:Mapped[str]=mapped_column(nullable=False)."},
      {"key":"pattern:docker+mongodb-only","topic":"docker","content":"// docker-compose.yml MongoDB only: services: db: image:mongo:7.0, healthcheck:{test:[mongosh,--eval,db.adminCommand('ping')],interval:15s}. app: depends_on:{db:{condition:service_healthy}}, environment:{MONGODB_URI:mongodb://db:27017/myapp}"},
      {"key":"pattern:docker+postgres-only","topic":"docker","content":"// docker-compose.yml PostgreSQL only: db: image:postgres:16-alpine, environment:{POSTGRES_DB,POSTGRES_USER,POSTGRES_PASSWORD}, healthcheck:{test:pg_isready -U postgres}. app: depends_on db, environment: DB_HOST:db DB_PORT:5432"},
      {"key":"nlp:entities-pt","topic":"nlp","content":"// PT→Entity: livro(s)→Book | usuário(s)→User | produto(s)→Product | pedido(s)→Order | categoria→Category | cliente→Customer | pagamento→Payment | tarefa→Task | livros→Book (plural→singular)"},
      {"key":"nlp:instructions-not-entities","topic":"nlp","content":"// NEVER create src/ folder from instructions: 'configure docker'→docker-compose NOT src/docker. 'mongoDb'→MongooseModule NOT src/mongodb. 'inglês'→code language NOT src/inglês. Only domain nouns become src/ folders."},
      {"key":"nlp:auth-detection","topic":"nlp","content":"// has_auth=true ONLY with: auth|autenticação|login|jwt|token|oauth|roles|permissions. 'usuários' alone→has_auth=FALSE. 'API de usuários'→User entity, NO auth. 'API com login JWT'→has_auth=TRUE"},
      {"key":"nlp:stack-db-detection","topic":"nlp","content":"// Stack: nestjs→NestJS|spring→Spring Boot|fastapi/python→FastAPI|dotnet/.net→ASP.NET. DB: mongodb/mongo→Mongoose|postgres/postgresql→TypeORM+pg|mysql→TypeORM+mysql2|redis→cache only NOT main db"},
      {"key":"pattern:error:module-not-found","topic":"common-errors","content":"// TS2307 './book/book.module' not found: CREATE src/book/book.module.ts with @Module({imports:[MongooseModule.forFeature([{name:Book.name,schema:BookSchema}])],providers:[BookService],controllers:[BookController]}) export class BookModule {}"},
      {"key":"pattern:error:findOneBy-mongoose","topic":"common-errors","content":"// TS2551 Model.findOneBy does not exist: findOneBy is TypeORM-only. Mongoose uses: findById(id), findOne({field:value}), findByIdAndUpdate, findByIdAndDelete. NEVER use findOneBy with Mongoose."},
      {"key":"pattern:error:partialtype","topic":"common-errors","content":"// PartialType import: ALWAYS from '@nestjs/mapped-types'. NEVER from '@nestjs/common' (doesn't exist there). NEVER from '@nestjs/swagger' (prefer mapped-types). Fix: import {PartialType} from '@nestjs/mapped-types'"},

  # ── Padrões de comunicação do usuário ─────────────────────────────────────
  {"key":"nlp:user-pt-br-informal","topic":"nlp","content":"""
# Vocabulário informal PT-BR que o usuário usa → o que quer dizer

Abreviações:
  oq = o que | tbm = também | tals = etc | pra/pro = para | n/ñ = não
  ia = inteligência artificial | mto/mt = muito | blz = beleza | vlw = valeu

Ações implícitas:
  "configura X"      → configure/setup X
  "tem o X"          → usa X como tecnologia (tem o mongoDb = usa MongoDB)
  "arruma X"         → fix/correct X
  "melhora X"        → improve X
  "faz um CRUD"      → create full CRUD (schema + service + module + controller + dto)
  "deixa só o necessário" → minimal, não adicionar extras
  "código em inglês" → todos os identificadores/arquivos em English

Exemplos de pedidos reais → o que o usuário quer:
  "configura o docker pra essa app que tem mongoDb"
    → gerar docker-compose.yml + Dockerfile com MongoDB (sem extras)
  "cria uma api de livros com mongo"
    → NestJS API, entidade Book (não Livros!), MongoDB, CRUD
  "faz a feature de auth com jwt"
    → adicionar módulo de autenticação com JWT + Passport
  "arruma o build"
    → devfix, corrigir erros TypeScript
  "não foi das tecnologias usadas"
    → gerou arquivos/configs para tecnologia diferente do pedido"""},

  {"key":"nlp:user-intent-patterns","topic":"nlp","content":"""
# Padrões de intenção do usuário

"CRUD de X com Y" → criar entidade X usando banco Y
  CRUD de livros com MongoDB → Book entity + Mongoose
  CRUD de produtos com postgres → Product entity + TypeORM

"configure o X" → configurar serviço/feature X (editar arquivos existentes)
  configure o swagger → instalar + editar main.ts
  configure o docker → criar docker-compose.yml + Dockerfile
  configure o CORS → editar main.ts

"adicione X" → adicionar feature nova
  adicione autenticação JWT → auth module
  adicione rate limiting → throttler

"tem o X" → usa X como dependência/tecnologia
  "app que tem o mongoDb" → db_type = mongodb

"só" / "apenas" / "somente" = MINIMAL — não adicionar NADA além do pedido
  "só o mongodb" → docker-compose só com MongoDB, SEM Redis/Kafka/Nginx
  "só o necessário" → mínimo funcional, sem extras

"código em inglês" → todos arquivos, variáveis, classes em English
  book.schema.ts (não livro.schema.ts)
  class Book (não class Livro)
  title, author, price (não titulo, autor, preco)"""},

  {"key":"nlp:user-corrections","topic":"nlp","content":"""
# O que o usuário quer dizer quando reclama

"criou coisas nada a ver" → gerou arquivos/pastas irrelevantes (src/docker, src/mongodb)
"não foi das tecnologias usadas" → .env ou config com tecnologia errada (postgres em projeto mongo)
"tá repetindo" → loop fazendo a mesma coisa
"não usa o treinamento" → training store não está sendo consultado na geração
"precisa entender melhor oq pede" → NLP está falhando na interpretação do pedido
"não evolui" → loop estudando os mesmos tópicos repetidamente
"ficou melhor" → aprovado, continuar com a abordagem

Quando usuário diz qualquer variação de "X não funciona" ou "X está errado":
  1. Identifica qual X especificamente
  2. Verifica a causa raiz
  3. Corrige o problema, não apenas o sintoma
  4. Documenta o anti-pattern para não repetir"""},
    ]
    for p in PATTERNS:
        save(p["key"], p["content"], topic=re.sub(r"[^\w]","_",p["topic"]), source="code_pattern")
    return len(PATTERNS)


def discover_new_topics(llm, model: str, known: list[str]) -> dict[str, list]:
    """Discovers new topics not yet in curriculum."""
    discovered = load_discovered()
    combined_known = list(set(known) | set(discovered.keys()))
    try:
        resp = llm.chat(
            model=model,
            messages=[{"role":"user","content":DISCOVERY_PROMPT.format(topics=", ".join(combined_known[:30]))}],
            system="Return only valid JSON array.",
            stream=False,
        )
        resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.strip())
        new = json.loads(resp)
        new_discovered = {}
        for t in new:
            if isinstance(t,dict) and "topic" in t and "searches" in t:
                if t["topic"] not in SEARCH_CURRICULUM and t["topic"] not in discovered:
                    new_discovered[t["topic"]] = t["searches"]
                    console.print(f"  [green]+[/green] Novo tópico descoberto: [cyan]{t['topic']}[/cyan]")
        if new_discovered:
            discovered.update(new_discovered)
            save_discovered(discovered)
        return new_discovered
    except Exception as e:
        console.print(f"  [dim]⚠ Discovery: {e}[/dim]")
        return {}


def validate_quick(llm, model: str) -> dict[str, float]:
    """Quick validation — returns {topic: score}."""
    from scripts.validate import VALIDATION_SUITE, validate_topic
    scores = {}
    for topic, questions in list(VALIDATION_SUITE.items())[:5]:
        try:
            result = validate_topic(topic, questions[:2], llm, model)  # only 2 per topic for speed
            scores[topic] = result.pass_rate
        except Exception:
            scores[topic] = -1
    return scores


def print_journal_summary(journal: dict, all_topics: list[str]):
    """Shows what was studied and what's pending."""
    now = time.time()
    done   = [(t,j) for t,j in journal.items() if topic_priority(j, now) == 0]
    todo   = [t for t in all_topics if topic_priority(journal.get(t), now) > 0]
    weak   = [(t,j) for t,j in journal.items() if 0 < j.last_score < 0.6]

    console.print(f"\n  [dim]📚 Diário: {len(done)} estudados · {len(todo)} pendentes · {len(weak)} fracos[/dim]")
    if weak:
        console.print(f"  [yellow]⚠ Fracos: {', '.join(t for t,_ in weak[:4])}[/yellow]")


ALTERNATIVE_PROMPTS = [
    "Suggest 5 advanced topics about error handling, testing, security or performance for: {topics}",
    "Suggest 5 integration topics between different frameworks/databases not yet covered: {topics}",
    "Suggest 5 DevOps, monitoring or deployment topics not yet covered: {topics}",
    "Suggest 5 topics about specific NestJS decorators, pipes, interceptors, guards patterns: {topics}",
    "Suggest 5 topics about database optimization, indexing, or caching patterns: {topics}",
]
_alt_prompt_idx = 0

def _discover_alternative(llm, model: str, known: list[str]) -> dict[str, list]:
    """Uses alternative prompts when main discovery returns nothing new."""
    global _alt_prompt_idx
    discovered = load_discovered()
    prompt_template = ALTERNATIVE_PROMPTS[_alt_prompt_idx % len(ALTERNATIVE_PROMPTS)]
    _alt_prompt_idx += 1

    prompt = f"{prompt_template.format(topics=', '.join(known[:20]))}\n\nReturn ONLY JSON: [{{\"topic\":\"name\",\"searches\":[\"query1\",\"query2\"]}}]"
    try:
        resp = llm.chat(
            model=model,
            messages=[{"role":"user","content":prompt}],
            system="Return only valid JSON array. Focus on specific, actionable topics.",
            stream=False,
        )
        resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.strip())
        topics = json.loads(resp)
        result = {}
        for t in topics:
            if isinstance(t,dict) and "topic" in t and "searches" in t:
                key = t["topic"]
                if key not in SEARCH_CURRICULUM and key not in discovered and key not in known:
                    result[key] = t["searches"]
                    discovered[key] = t["searches"]
                    console.print(f"  [green]+[/green] Alt descoberto: [cyan]{key}[/cyan]")
        if result:
            save_discovered(discovered)
        return result
    except Exception as e:
        console.print(f"  [dim]⚠ Alt discovery: {e}[/dim]")
        return {}


def run_knowledge_check() -> dict[str, float]:
    """
    Roda a Fase 1 do validate (sem LLM) para medir score de cada tópico.
    Retorna {nome: score_0_a_1}.
    Rápido — só lê o vector store, sem chamada LLM.
    """
    try:
        from scripts.validate import KNOWLEDGE_CHECKS, check_knowledge
        scores: dict[str, float] = {}
        for check in KNOWLEDGE_CHECKS:
            passed, score, _ = check_knowledge(check)
            name = check["name"]
            scores[name] = score / check["weight"]
        return scores
    except Exception as e:
        console.print(f"  [dim]⚠ Knowledge check: {e}[/dim]")
        return {}


def retrain_weak_topics(scores: dict[str, float], llm, model: str) -> int:
    """
    Retreina tópicos com score abaixo do threshold.
    Usa os CRITICAL_PATTERNS do validate.py para injetar respostas certas.
    """
    try:
        from scripts.validate import CRITICAL_PATTERNS, force_train
        from tools.vector_store import save, backfill_embeddings

        # Salva todos os padrões críticos (sempre — são a base)
        saved = 0
        for key, topic, pat_content in CRITICAL_PATTERNS:
            save(key, pat_content, topic=topic, source="critical_pattern")
            saved += 1

        # Gera embeddings para os novos padrões
        n_emb = backfill_embeddings()
        if n_emb:
            console.print(f"  [green]✓[/green] {n_emb} embedding(s) gerado(s)")

        return saved
    except Exception as e:
        console.print(f"  [dim]⚠ Retrain: {e}[/dim]")
        return 0


def main():
    parser = argparse.ArgumentParser(description="DevAI Auto-Study v5 — Smart loop")
    parser.add_argument("--group",     default="all", choices=list(TOPIC_GROUPS.keys()))
    parser.add_argument("--topics",    nargs="+")
    parser.add_argument("--quick",     action="store_true")
    parser.add_argument("--intensive", action="store_true")
    parser.add_argument("--loop",      action="store_true")
    parser.add_argument("--interval",  type=int, default=1800)
    parser.add_argument("--validate",  action="store_true")
    parser.add_argument("--force",     action="store_true", help="Força re-estudo mesmo dos já estudados")
    parser.add_argument("--status",    action="store_true", help="Mostra o status do diário e sai")
    args = parser.parse_args()

    if args.quick: args.group = "quick"

    console.print(Panel.fit(
        "[bold cyan]⚡ DevAI Auto-Study v5[/bold cyan]\n"
        "[dim]Loop inteligente — não repete o que já foi estudado[/dim]",
        border_style="cyan",
    ))

    # Status only
    if args.status:
        journal = load_journal()
        discovered = load_discovered()
        all_t = TOPIC_GROUPS.get(args.group, TOPIC_GROUPS["all"])
        now = time.time()
        t = Table(title="📚 Diário de Estudo", border_style="dim")
        t.add_column("Tópico",   style="cyan",   max_width=35)
        t.add_column("Vezes",    width=6,  justify="center")
        t.add_column("Score",    width=7,  justify="center")
        t.add_column("Há",       width=8)
        t.add_column("Ação",     style="dim")
        for topic in all_t:
            e = journal.get(topic)
            if e is None:
                t.add_row(topic, "0", "—", "—", "[yellow]estudar[/yellow]")
            else:
                hours = int((now - e.last_studied) / 3600)
                score_str = f"{e.last_score*100:.0f}%" if e.last_score >= 0 else "—"
                prio = topic_priority(e, now)
                action = "[green]ok[/green]" if prio == 0 else "[yellow]revisar[/yellow]" if prio < 70 else "[red]urgente[/red]"
                t.add_row(topic, str(e.times_studied), score_str, f"{hours}h", action)
        console.print(t)
        console.print(f"\n  Descobertos: {len(discovered)} novos tópicos")
        return

    try:
        llm, model = load_llm()
        console.print(f"  [green]✓[/green] Modelo: {model}")
    except Exception as e:
        console.print(f"[red]✗ Ollama: {e}[/red]"); sys.exit(1)

    try:
        from tools.embeddings import model_available, pull_model_if_needed
        if not model_available(): pull_model_if_needed()
        else: console.print("  [green]✓[/green] Embeddings: nomic-embed-text")
    except Exception:
        console.print("  [yellow]○[/yellow] Embeddings: fallback keyword")

    # Load state
    journal   = load_journal()
    discovered = load_discovered()

    # Build topic list
    if args.topics:
        base_topics = [t for t in args.topics if t in SEARCH_CURRICULUM]
    else:
        base_topics = TOPIC_GROUPS.get(args.group, TOPIC_GROUPS["all"])

    all_curriculum = {**SEARCH_CURRICULUM, **discovered}

    print_journal_summary(journal, base_topics)
    console.print(f"  Modo: {'intensivo 🔥' if args.intensive else 'normal'} | Loop: {'sim' if args.loop else 'não'}\n")

    cycle = 1
    while True:
        now = time.time()
        console.print(Rule(f"[bold cyan]Ciclo {cycle} — {time.strftime('%H:%M %d/%m')}[/bold cyan]"))

        # 0. Sincroniza vetores com patterns JSON (garante embeddings atualizados)
        console.print(Rule("[cyan]0 — Sincronizando vetores ↔ patterns[/cyan]"))
        try:
            from tools.vector_store import sync_patterns_to_vectors
            n_sync = sync_patterns_to_vectors()
            if n_sync:
                console.print(f"  [green]✓[/green] {n_sync} pattern(s) sincronizado(s)")
            else:
                console.print(f"  [dim]✓ Vetores já sincronizados[/dim]")
        except Exception as e:
            console.print(f"  [dim]⚠ Sync: {e}[/dim]")

        # 1. Sempre salva padrões de código (idempotente)
        console.print(Rule("[cyan]1 — Padrões de código[/cyan]"))
        n_pat = save_code_patterns()
        console.print(f"  [green]✓[/green] {n_pat} padrões atualizados")

        # 2. Seleciona tópicos a estudar neste ciclo
        console.print(Rule("[cyan]2 — Seleção de tópicos[/cyan]"))
        priorities = {
            t: topic_priority(journal.get(t), now)
            for t in base_topics
        }
        # Add discovered topics
        for t in discovered:
            if t not in priorities:
                priorities[t] = topic_priority(journal.get(t), now)

        to_study = sorted(
            [(t, p) for t, p in priorities.items() if p > 0 or args.force],
            key=lambda x: x[1], reverse=True
        )

        if not to_study:
            console.print("  [green]✓ Base atualizada — buscando novos tópicos...[/green]")
        else:
            console.print(f"  {len(to_study)} tópico(s) para estudar (de {len(priorities)} total)")
            console.print(f"  [dim]Pulados (já estudados): {len(priorities) - len(to_study)}[/dim]")

        # 3. Estuda cada tópico selecionado
        total_saved = n_pat
        for topic, priority in to_study:
            searches = all_curriculum.get(topic, [])
            if not searches:
                continue
            icon = "🔥" if priority >= 80 else "📖" if priority >= 40 else "🔄"
            console.print(Rule(f"[cyan]{icon} {topic} (prio:{priority:.0f})[/cyan]"))
            n = study_topic(topic, searches, llm, model, intensive=args.intensive)
            total_saved += n

            # Atualiza o diário
            entry = journal.get(topic) or TopicEntry(topic=topic)
            entry.last_studied  = time.time()
            entry.times_studied += 1
            entry.items_saved   += n
            journal[topic] = entry
            save_journal(journal)

            console.print(f"  [green]✓[/green] {n} itens salvos")

        # 4. Descobre novos tópicos — SEMPRE roda, mesmo quando base está atualizada
        console.print(Rule("[cyan]3 — Descoberta de novos tópicos[/cyan]"))
        # Pede ao LLM mais sugestões baseado no que já foi estudado
        all_known = list(set(list(journal.keys()) + base_topics))
        new = discover_new_topics(llm, model, all_known)
        if new:
            for t, searches in new.items():
                console.print(f"  [dim]📖 Estudando: {t}[/dim]")
                n = study_topic(t, searches, llm, model, intensive=args.intensive)
                entry = TopicEntry(topic=t, source="discovered")
                entry.last_studied = time.time(); entry.times_studied = 1; entry.items_saved = n
                journal[t] = entry
                total_saved += n
            save_journal(journal)
            console.print(f"  [green]✓[/green] {len(new)} novo(s) tópico(s) estudados")
        else:
            # Descobre com prompt diferente se LLM não sugeriu nada novo
            console.print("  [dim]Tentando prompt alternativo...[/dim]")
            alt_new = _discover_alternative(llm, model, all_known)
            if alt_new:
                for t, searches in alt_new.items():
                    n = study_topic(t, searches, llm, model, intensive=args.intensive)
                    entry = TopicEntry(topic=t, source="discovered_alt")
                    entry.last_studied = time.time(); entry.times_studied = 1; entry.items_saved = n
                    journal[t] = entry; total_saved += n
                save_journal(alt_new)
                console.print(f"  [green]✓[/green] {len(alt_new)} tópico(s) alternativos estudados")

        # 5. Embeddings
        try:
            from tools.vector_store import backfill_embeddings, stats
            n_emb = backfill_embeddings()
            st = stats()
            if n_emb: console.print(f"  [green]✓[/green] {n_emb} embedding(s)")
        except Exception: st = {}

        # 6. Knowledge check + retreino adaptativo (sempre roda, rápido)
        console.print(Rule("[cyan]4 — Knowledge Check + Retreino Adaptativo[/cyan]"))
        MAX_RETRAIN_ROUNDS = 5
        for retrain_round in range(1, MAX_RETRAIN_ROUNDS + 1):
            scores = run_knowledge_check()
            if not scores:
                break

            total   = sum(scores.values())
            max_s   = len(scores)
            overall = total / max_s if max_s else 0
            bar     = "█" * int(overall * 10) + "░" * (10 - int(overall * 10))
            color   = "green" if overall >= SCORE_THRESHOLD else "yellow" if overall >= 0.5 else "red"
            console.print(f"  [{color}]Round {retrain_round}: {overall*100:.0f}% [{bar}][/{color}]")

            # Mostra detalhes dos que falharam
            weak = [(k, v) for k, v in scores.items() if v < SCORE_THRESHOLD]
            if weak:
                for name, score in weak[:5]:
                    console.print(f"  [dim]  ✗ {name[:50]}: {score*100:.0f}%[/dim]")

            # Atualiza journal com score médio
            for t_key in journal:
                journal[t_key].last_score = overall

            if overall >= SCORE_THRESHOLD:
                console.print(f"  [green]✅ Score {overall*100:.0f}% ≥ {SCORE_THRESHOLD*100:.0f}% — aprovado![/green]")
                break

            # Retreina padrões críticos e pesquisa web dos tópicos fracos
            console.print(f"  [yellow]→ {len(weak)} check(s) fracos — retreinando (round {retrain_round}/{MAX_RETRAIN_ROUNDS})...[/yellow]")
            n_saved = retrain_weak_topics(scores, llm, model)
            if n_saved:
                console.print(f"  [green]✓[/green] {n_saved} padrão(ões) reforçado(s)")

            # Pesquisa web adicional para tópicos mapeados como fracos
            weak_topic_map = {
                "Mongoose": ["nestjs_mongodb"],
                "findOneBy": ["nestjs_mongodb"],
                "MongooseModule": ["nestjs_mongodb"],
                "livros": ["nlp_patterns"],
                "usuários": ["nlp_patterns"],
                "docker": ["docker_patterns"],
                "PartialType": ["nestjs_auth"],
                "TS2307": ["common_errors"],
                "Spring": ["spring_mongodb"],
                "FastAPI": ["fastapi_mongodb"],
            }
            all_c = {**SEARCH_CURRICULUM, **load_discovered()}
            for name, score in weak[:3]:
                for keyword, study_keys in weak_topic_map.items():
                    if keyword.lower() in name.lower():
                        for sk in study_keys:
                            if sk in all_c:
                                n = study_topic(sk, all_c[sk][:2], llm, model, intensive=True)
                                if n: console.print(f"  [dim]+ {n} pesquisa(s) web ({sk})[/dim]")
                        break

            # Re-gera embeddings após retreino
            try:
                from tools.vector_store import backfill_embeddings
                backfill_embeddings()
            except Exception:
                pass

        save_journal(journal)

        # Summary
        elapsed = int(time.time() - now)
        m, s = divmod(elapsed, 60)
        studied_count = len([t for t,_ in to_study])
        skipped_count = len(priorities) - studied_count

        console.print(Panel.fit(
            f"[bold green]✅ Ciclo {cycle} — {m:02d}m{s:02d}s[/bold green]\n\n"
            f"  Estudados este ciclo: {studied_count}\n"
            f"  Pulados (já OK):      {skipped_count}\n"
            f"  Itens salvos:         {total_saved}\n"
            f"  Total no banco:       {st.get('total',0)}\n"
            f"  Descobertos total:    {len(load_discovered())}",
            border_style="green",
        ))
        console.print("[dim]git add training/ && git commit -m 'training: update'[/dim]")
        # Auto-atualiza documentação e commita
        try:
            from scripts.update_docs import update_readme
            if update_readme():
                console.print("[dim]✓ README.md atualizado[/dim]")
        except Exception:
            pass
        try:
            from tools.vector_store import auto_commit
            committed = auto_commit()
            if committed:
                console.print("[green]✓ Commitado e push realizado[/green]")
        except Exception:
            pass

        # Export and commit
        try:
            from tools.vector_store import export_markdown
            export_markdown()
        except Exception: pass

        if not args.loop: break
        console.print(f"\n[dim]Próximo ciclo em {args.interval//60}min...[/dim]")
        time.sleep(args.interval)
        cycle += 1


if __name__ == "__main__":
    main()
