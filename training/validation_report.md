# DevAI Validation Report
*2026-06-06 08:47*

## Score: 5% `[█░░░░░░░░░░░░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nlp | 3.3/15.0 | 22% | ❌ |
| nestjs-mongodb | 0.0/15.0 | 0% | ❌ |
| nestjs-typeorm | 0.0/4.0 | 0% | ❌ |
| nestjs-auth | 0.0/5.0 | 0% | ❌ |
| nestjs-core | 0.0/4.0 | 0% | ❌ |
| docker | 0.0/4.0 | 0% | ❌ |
| spring-mongodb | 0.0/4.0 | 0% | ❌ |
| fastapi | 0.0/4.0 | 0% | ❌ |
| common-errors | 0.0/6.0 | 0% | ❌ |

## ❌ Retreinar urgente

### nestjs-mongodb (0%)
- ✗ NestJS Mongoose: required field uses ! or ? TypeScript modifier?
  - Missing: `!`
- ✗ NestJS Mongoose schema: @Prop({required:true}) maps to field!:str
  - Missing: `field!, !:`
- ✗ NestJS Mongoose service: which method to use instead of findOneBy
  - Missing: `findById, findOne`
- ✗ NestJS Mongoose module: which import to use, MongooseModule.forFe
  - Missing: `MongooseModule.forFeature`
- ✗ NestJS app.module.ts for MongoDB: what module to add for database
  - Missing: `MongooseModule.forRoot, MONGODB_URI`

### nestjs-typeorm (0%)
- ✗ NestJS TypeORM: which decorator for primary UUID column?
  - Missing: `@PrimaryGeneratedColumn, uuid`
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Missing: `@InjectRepository`

### nestjs-auth (0%)
- ✗ NestJS PartialType: from @nestjs/mapped-types or @nestjs/common?
  - Missing: `@nestjs/mapped-types`
- ✗ NestJS JWT: which class to extend for JwtStrategy?
  - Missing: `PassportStrategy, Strategy`

### nestjs-core (0%)
- ✗ NestJS ValidationPipe: what options to set for whitelist and tran
  - Missing: `whitelist, transform`
- ✗ NestJS Swagger setup in main.ts: which classes to use?
  - Missing: `DocumentBuilder, SwaggerModule`

### nlp (22%)
- ✗ User says 'CRUD de livros com MongoDB'. What is the entity name?
  - Missing: `Book`
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, docker-compose, Dockerfile`
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `false, não`
- ✗ User requests 'API with MongoDB and Docker only'. Should Redis ap
  - Missing: `não, only, apenas`

### docker (0%)
- ✗ MongoDB healthcheck in docker-compose: which command?
  - Missing: `mongosh, adminCommand, ping`
- ✗ docker-compose depends_on: how to wait for a healthy service?
  - Missing: `condition, service_healthy`

### spring-mongodb (0%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Missing: `@Document`
- ✗ Spring Data MongoDB: extends MongoRepository or JpaRepository?
  - Missing: `MongoRepository`

### fastapi (0%)
- ✗ FastAPI MongoDB: which async driver to use?
  - Missing: `motor, Motor, AsyncIOMotorClient`
- ✗ FastAPI: Pydantic v2 model method to serialize: model_dump or dic
  - Missing: `model_dump`

### common-errors (0%)
- ✗ NestJS TS2307: module not found book.module — what is the fix?
  - Missing: `create, module.ts, BookModule, @Module`
- ✗ NestJS error: PartialType from @nestjs/common — what is correct i
  - Missing: `@nestjs/mapped-types`

## Como corrigir

```bash
# Fix automático (retreina + re-valida)
python scripts/validate.py --fix

# Forçar retreinamento específico
python scripts/validate.py --fix --topic nestjs-mongodb
python scripts/validate.py --fix --topic nestjs-typeorm
python scripts/validate.py --fix --topic nestjs-auth

# Overnight
./scripts/study.sh --group all --loop --validate --intensive
```