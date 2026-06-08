"""
Manifests — lista FIXA de arquivos por stack.
Princípio: SOLID mas limpo. Menos arquivos, mais coesos.

NestJS por entidade: 6 arquivos (não 12)
  - entity.ts      → domínio TypeORM
  - entity.dto.ts  → Create + Update DTO num único arquivo
  - entity.service.ts  → usa Repository<Entity> diretamente (sem wrapper)
  - entity.controller.ts
  - entity.module.ts
  - entity.spec.ts

Sem arquivos de interface separados, sem barrel index.ts, sem repository wrapper.
Repository<Entity> DO TypeORM já é a abstração (DIP satisfeito).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileSpec:
    path:        str
    file_type:   str
    description: str
    entity:      str = ""
    required:    bool = True


# ─── NestJS ───────────────────────────────────────────────────────────────────

def nestjs_manifest(name: str, pkg: str, entities: list[str], has_auth: bool,
                    db_type: str = "postgres") -> list[FileSpec]:
    """NestJS manifest — suporta PostgreSQL, MySQL, SQLite, MongoDB."""
    files: list[FileSpec] = []
    mods = entities + (["Auth"] if has_auth else [])
    mod_imports = ", ".join(f"{e}Module" for e in mods)

    # Configuração dinâmica do módulo de banco
    from tools.db_strategy import get_strategy, nestjs_db_module_config
    db_strategy = get_strategy(db_type)
    db_mod_config = nestjs_db_module_config(db_strategy, name)

    # Infra base
    files += [
        FileSpec("src/main.ts", "bootstrap",
            "NestJS bootstrap with ValidationPipe({whitelist:true,transform:true,forbidNonWhitelisted:true}), "
            "Swagger DocumentBuilder with title/version/BearerAuth/setup('api'), "
            "app.enableCors(), app.listen(process.env.PORT||3000). "
            "Import all from '@nestjs/core', '@nestjs/common', '@nestjs/swagger'"),

        FileSpec("src/app.module.ts", "root-module",
            f"@Module({{ imports: [ConfigModule.forRoot({{ isGlobal: true }}), "
            f"{db_mod_config}, "
            f"{mod_imports}] }}) AppModule. "
            f"Import ConfigModule from @nestjs/config. "
            f"{'Import MongooseModule from @nestjs/mongoose and connect with MONGODB_URI env var' if db_strategy.is_nosql else 'Import TypeOrmModule from @nestjs/typeorm and connect using DB_HOST/PORT/NAME/USER/PASS env vars'}. "
            f"DO NOT add JwtModule, BullModule, CacheModule, WinstonModule, PassportModule, or any other module not listed above."),

        FileSpec("src/common/http-exception.filter.ts", "filter",
            "@Catch() AllExceptionsFilter implements ExceptionFilter. "
            "catch(exception, host): returns {{statusCode, message, timestamp, path}}. "
            "import {{ExceptionFilter,Catch,ArgumentsHost,HttpException,HttpStatus}} from '@nestjs/common'"),
    ]

    # ── Auth ────────────────────────────────────────────────────────────
    if has_auth:
        files += [
            FileSpec("src/auth/auth.dto.ts", "dto",
                "LoginDto: @IsEmail() email, @MinLength(6) password. "
                "RegisterDto: @IsString() @IsNotEmpty() name, @IsEmail() email, @MinLength(6) password. "
                "All from class-validator. @ApiProperty() on each field from @nestjs/swagger"),

            FileSpec("src/auth/auth.service.ts", "service",
                "@Injectable() AuthService. inject UsersService and JwtService. "
                "async validateUser(email,pass): finds user, compares bcrypt, returns user or null. "
                "async login(user): return {access_token: this.jwt.sign({sub:user.id,email:user.email})}. "
                "async register(dto:RegisterDto): hash password with bcrypt, create user, return login"),

            FileSpec("src/auth/jwt.strategy.ts", "strategy",
                "@Injectable() JwtStrategy extends PassportStrategy(Strategy). "
                "constructor: super({jwtFromRequest:ExtractJwt.fromAuthHeaderAsBearerToken(), "
                "secretOrKey:configService.get('JWT_SECRET')}). "
                "async validate(payload): return {id:payload.sub, email:payload.email}"),

            FileSpec("src/auth/jwt.guard.ts", "guard",
                "@Injectable() export class JwtAuthGuard extends AuthGuard('jwt') {}"),

            FileSpec("src/auth/auth.controller.ts", "controller",
                "@ApiTags('auth') @Controller('auth'). "
                "POST /login: @UseGuards(LocalAuthGuard) returns JWT. "
                "POST /register: calls authService.register(dto:RegisterDto)"),

            FileSpec("src/auth/local.strategy.ts", "strategy",
                "@Injectable() LocalStrategy extends PassportStrategy(Strategy,'local'). "
                "usernameField:'email'. validate(email,pass): calls authService.validateUser, throws UnauthorizedException if null"),

            FileSpec("src/auth/auth.module.ts", "module",
                "@Module imports:[JwtModule.registerAsync({useFactory:(c)=>({secret:c.get('JWT_SECRET'),"
                "signOptions:{expiresIn:c.get('JWT_EXPIRES_IN','7d')}}), inject:[ConfigService]}), "
                "PassportModule, UsersModule]. providers:[AuthService, JwtStrategy, LocalStrategy]. "
                "controllers:[AuthController]"),

            FileSpec("src/auth/auth.spec.ts", "test",
                "Jest unit tests for AuthService. Mock JwtService and UsersService. "
                "Tests: login returns token, login with wrong password throws, register creates user"),
        ]

    # ── Por entidade: 6 arquivos, limpos ─────────────────────────────────
    for entity in entities:
        e  = entity          # PascalCase
        el = entity.lower()  # kebab
        ep = el + "s"        # plural

        files += [
            # 1. Entity
            FileSpec(f"src/{el}/{el}.entity.ts", "entity",
                f"@Entity('{ep}') export class {e}Entity. "
                f"@PrimaryGeneratedColumn('uuid') id: string. "
                f"Domain columns: add relevant @Column() fields for {e}. "
                f"@CreateDateColumn() createdAt: Date. @UpdateDateColumn() updatedAt: Date. "
                f"imports from 'typeorm'. @ApiProperty() on each field from @nestjs/swagger",
                entity=e),

            # 2. DTO (create + update in one file)
            FileSpec(f"src/{el}/{el}.dto.ts", "dto",
                f"export class Create{e}Dto: all required domain fields with @ApiProperty() and "
                f"class-validator decorators (@IsString, @IsNotEmpty, @IsNumber, @IsEmail as needed). "
                f"export class Update{e}Dto extends PartialType(Create{e}Dto) {{}}. "
                f"import PartialType from '@nestjs/mapped-types'. "
                f"import ApiProperty from '@nestjs/swagger'. "
                f"import validators from 'class-validator'",
                entity=e),

            # 3. Service (uses Repository<Entity> directly — DIP via TypeORM)
            FileSpec(f"src/{el}/{el}.service.ts", "service",
                f"@Injectable() export class {e}Service. "
                f"constructor(@InjectRepository({e}Entity) private repo: Repository<{e}Entity>). "
                f"import Repository from 'typeorm'. import InjectRepository from '@nestjs/typeorm'. "
                f"findAll(): this.repo.find(). "
                f"findOne(id:string): this.repo.findOneBy({{id}}) then throw NotFoundException if null. "
                f"create(dto:Create{e}Dto): this.repo.save(this.repo.create(dto)). "
                f"update(id,dto:Update{e}Dto): findOne then Object.assign then save. "
                f"remove(id): findOne then this.repo.remove(entity). "
                f"All methods async, return Promise",
                entity=e),

            # 4. Controller
            FileSpec(f"src/{el}/{el}.controller.ts", "controller",
                f"@ApiTags('{ep}') @Controller('{ep}') export class {e}Controller. "
                f"inject {e}Service. "
                f"@Get() findAll(): service.findAll(). "
                f"@Get(':id') findOne(@Param('id') id:string): service.findOne(id). "
                f"@Post() @ApiCreatedResponse() create(@Body() dto:Create{e}Dto): service.create(dto). "
                f"@Patch(':id') update(@Param('id') id, @Body() dto:Update{e}Dto): service.update(id,dto). "
                f"@Delete(':id') @HttpCode(204) remove(@Param('id') id): service.remove(id). "
                f"Use @UseGuards(JwtAuthGuard) if auth is needed",
                entity=e),

            # 5. Module
            FileSpec(f"src/{el}/{el}.module.ts", "module",
                f"@Module({{ imports:[TypeOrmModule.forFeature([{e}Entity])], "
                f"providers:[{e}Service], controllers:[{e}Controller], "
                f"exports:[{e}Service] }}) export class {e}Module {{}}",
                entity=e),

            # 6. Tests
            FileSpec(f"src/{el}/{el}.spec.ts", "test",
                f"Jest unit tests for {e}Service. "
                f"mock repository: const mockRepo = {{ find:jest.fn(), findOneBy:jest.fn(), "
                f"create:jest.fn(), save:jest.fn(), remove:jest.fn() }}. "
                f"beforeEach: create TestingModule with {e}Service and "
                f"{{provide:getRepositoryToken({e}Entity), useValue:mockRepo}}. "
                f"Tests: findAll returns array, findOne returns entity, "
                f"findOne throws NotFoundException when null, create calls save, remove calls remove",
                entity=e),
        ]

    return files



def nestjs_mongoose_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    """NestJS + MongoDB/Mongoose manifest — schemas instead of entities."""
    files: list[FileSpec] = []
    mods = entities + (["Auth"] if has_auth else [])
    mod_imports = ", ".join(f"{e}Module" for e in mods)

    files += [
        FileSpec("src/main.ts", "bootstrap",
            "NestJS bootstrap: ValidationPipe, Swagger, CORS, listen(PORT)"),

        FileSpec("src/app.module.ts", "root-module",
            f"@Module imports:[ConfigModule.forRoot({{isGlobal:true}}), "
            f"MongooseModule.forRoot(configService.get('MONGODB_URI','mongodb://localhost:27017/{name}')), "
            f"{mod_imports}] AppModule. "
            f"Import MongooseModule from '@nestjs/mongoose'"),

        FileSpec("src/common/http-exception.filter.ts", "filter",
            "@Catch() AllExceptionsFilter implements ExceptionFilter. Returns {statusCode, message, timestamp, path}"),
    ]

    if has_auth:
        files += [
            FileSpec("src/auth/auth.dto.ts", "dto",
                "LoginDto: @IsEmail() email, @MinLength(6) password from class-validator. "
                "RegisterDto: name, email, password with @ApiProperty from @nestjs/swagger"),
            FileSpec("src/auth/auth.service.ts", "service",
                "@Injectable() AuthService. Uses UsersService and JwtService. "
                "validateUser(email,pass): find user, bcrypt.compare, return user or null. "
                "login(user): jwt.sign({sub:user._id,email}). register(dto): hash pw, create user"),
            FileSpec("src/auth/jwt.strategy.ts", "strategy",
                "@Injectable() JwtStrategy extends PassportStrategy(Strategy). "
                "super({jwtFromRequest:ExtractJwt.fromAuthHeaderAsBearerToken(), secretOrKey:config.get('JWT_SECRET')}). "
                "validate(payload): return {id:payload.sub, email:payload.email}"),
            FileSpec("src/auth/local.strategy.ts", "strategy",
                "@Injectable() LocalStrategy extends PassportStrategy(Strategy,'local'). usernameField:'email'. "
                "validate: authService.validateUser, throw UnauthorizedException if null"),
            FileSpec("src/auth/jwt.guard.ts", "guard",
                "@Injectable() export class JwtAuthGuard extends AuthGuard('jwt') {}"),
            FileSpec("src/auth/auth.controller.ts", "controller",
                "@ApiTags('auth') @Controller('auth'). POST /login @UseGuards(LocalAuthGuard). POST /register"),
            FileSpec("src/auth/auth.module.ts", "module",
                "@Module imports:[JwtModule.registerAsync with JWT_SECRET, PassportModule, UsersModule]. "
                "providers:[AuthService, JwtStrategy, LocalStrategy]. controllers:[AuthController]"),
        ]

    for entity in entities:
        e  = entity
        el = entity.lower()
        ep = el + "s"

        files += [
            FileSpec(f"src/{el}/{el}.schema.ts", "schema",
                f"@Schema({{timestamps:true}}) export class {e}. "
                f"REQUIRED props: @Prop({{required:true}}) fieldName!: Type (with ! non-null assertion). "
                f"OPTIONAL props: @Prop() fieldName?: Type (with ? and NO !). "
                f"export type {e}Document = HydratedDocument<{e}>. "
                f"export const {e}Schema = SchemaFactory.createForClass({e}). "
                f"Add @ApiProperty() for required, @ApiPropertyOptional() for optional. "
                f"Add class-validator decorators (@IsString, @IsNotEmpty, @IsEmail, etc).",
                entity=e),

            FileSpec(f"src/{el}/{el}.dto.ts", "dto",
                f"export class Create{e}Dto with @ApiProperty() and class-validator decorators. "
                f"export class Update{e}Dto extends PartialType(Create{e}Dto). "
                f"import PartialType from '@nestjs/mapped-types' (NOT @nestjs/common)",
                entity=e),

            FileSpec(f"src/{el}/{el}.service.ts", "service",
                f"@Injectable() {e}Service. "
                f"@InjectModel({e}.name) private model: Model<{e}Document>. "
                f"findAll(): model.find().sort({{createdAt:-1}}).exec(). "
                f"findOne(id:string): model.findById(id).exec() → throw NotFoundException if null. "
                f"create(dto): new this.model(dto).save(). "
                f"update(id,dto): model.findByIdAndUpdate(id,{{$set:dto}},{{new:true}}).exec(). "
                f"remove(id): model.findByIdAndDelete(id).exec()",
                entity=e),

            FileSpec(f"src/{el}/{el}.controller.ts", "controller",
                f"@ApiTags('{ep}') @Controller('{ep}') {e}Controller. "
                f"@Get() findAll. @Get(':id') findOne. @Post() create. @Patch(':id') update. "
                f"@Delete(':id') @HttpCode(204) remove. @UseGuards(JwtAuthGuard) if auth needed. "
                f"import JwtAuthGuard from '../auth/jwt.guard' (correct path)",
                entity=e),

            FileSpec(f"src/{el}/{el}.module.ts", "module",
                f"@Module imports:[MongooseModule.forFeature([{{name:{e}.name, schema:{e}Schema}}])]. "
                f"providers:[{e}Service]. controllers:[{e}Controller]. exports:[{e}Service]",
                entity=e),

            FileSpec(f"src/{el}/{el}.spec.ts", "test",
                f"Jest tests for {e}Service using getModelToken({e}.name). "
                f"Mock Model with find/findById/findByIdAndUpdate/findByIdAndDelete chained with exec(). "
                f"Mock constructor for new this.model(dto).save(). "
                f"Tests: findAll, findOne success, findOne throws NotFoundException, create, update, remove",
                entity=e),
        ]

    return files


# ─── Spring Boot ──────────────────────────────────────────────────────────────# ─── Spring Boot ──────────────────────────────────────────────────────────────

def spring_boot_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    base = f"src/main/java/{pkg.replace('.', '/')}"
    res  = "src/main/resources"
    test = f"src/test/java/{pkg.replace('.', '/')}"
    files: list[FileSpec] = []

    files += [
        FileSpec(f"{base}/{_pascal(name)}Application.java", "bootstrap",
            "@SpringBootApplication @EnableJpaAuditing main class"),
        FileSpec(f"{res}/application.yml", "config",
            "spring.datasource url/username/password/driver. "
            "spring.jpa.hibernate.ddl-auto: validate. "
            "spring.jpa.show-sql: false. springdoc.api-docs.path: /api-docs. "
            "server.port: 8080"),
        FileSpec(f"{res}/application-dev.yml", "config",
            "spring.jpa.hibernate.ddl-auto: create-drop. spring.jpa.show-sql: true"),
        FileSpec(f"{base}/config/OpenApiConfig.java", "config",
            "@Configuration OpenAPI bean with title, version, JWT bearer scheme"),
        FileSpec(f"{base}/exception/GlobalHandler.java", "exception",
            "@RestControllerAdvice @Slf4j. @ExceptionHandler(EntityNotFoundException): 404. "
            "@ExceptionHandler(MethodArgumentNotValidException): 400 with field errors. "
            "@ExceptionHandler(Exception): 500"),
        FileSpec(f"{base}/exception/ApiError.java", "dto",
            "record ApiError(int status, String message, String path, LocalDateTime timestamp) {}"),
        FileSpec(f"{base}/audit/AuditEntity.java", "base",
            "@MappedSuperclass @Getter. @CreatedDate LocalDateTime createdAt. "
            "@LastModifiedDate LocalDateTime updatedAt. @EntityListeners(AuditingEntityListener.class)"),
    ]

    if has_auth:
        files += [
            FileSpec(f"{base}/auth/AuthController.java", "controller",
                "@RestController @RequestMapping('/api/v1/auth'). "
                "POST /login: returns JwtResponse. POST /register: creates user"),
            FileSpec(f"{base}/auth/AuthService.java", "service",
                "@Service. login(LoginRequest): validates, generates JWT. "
                "register(RegisterRequest): encodes password, saves user"),
            FileSpec(f"{base}/auth/JwtService.java", "service",
                "@Service. generateToken(username): HS256 HMAC. validateToken(token): checks expiry"),
            FileSpec(f"{base}/auth/SecurityConfig.java", "config",
                "@Configuration @EnableWebSecurity. Stateless, JWT filter, permits /auth/**, /api-docs/**"),
            FileSpec(f"{base}/auth/JwtFilter.java", "filter",
                "OncePerRequestFilter: extract Bearer, validate, set SecurityContext"),
            FileSpec(f"{base}/auth/dto/AuthDtos.java", "dto",
                "record LoginRequest(@NotBlank String email, @NotBlank String password). "
                "record RegisterRequest(@NotBlank String name, @Email String email, @Size(min=6) String password). "
                "record JwtResponse(String token)"),
        ]

    for entity in entities:
        e  = _pascal(entity)
        el = entity.lower()

        files += [
            FileSpec(f"{base}/{el}/{e}Entity.java", "entity",
                f"@Entity @Table(name='{el}s') extending AuditEntity. "
                f"@Id @GeneratedValue(UUID). Domain @Column fields. "
                f"Lombok: @Getter @Setter @Builder @NoArgsConstructor @AllArgsConstructor"),
            FileSpec(f"{base}/{el}/{e}Repository.java", "repository",
                f"public interface {e}Repository extends JpaRepository<{e}Entity, UUID> {{}}"),
            FileSpec(f"{base}/{el}/{e}Dto.java", "dto",
                f"record {e}Request with @NotNull domain fields. "
                f"record {e}Response(UUID id, fields, LocalDateTime createdAt, LocalDateTime updatedAt). "
                f"Inner class or separate records in same file"),
            FileSpec(f"{base}/{el}/{e}Service.java", "service",
                f"@Service @RequiredArgsConstructor @Transactional(readOnly=true). "
                f"inject {e}Repository. "
                f"findAll():List, findById(UUID) throws EntityNotFoundException, "
                f"@Transactional create({e}Request), update(UUID,{e}Request), delete(UUID)"),
            FileSpec(f"{base}/{el}/{e}Controller.java", "controller",
                f"@RestController @RequestMapping('/api/v1/{el}s') @RequiredArgsConstructor. "
                f"@GetMapping, @GetMapping/:id, @PostMapping, @PutMapping/:id, @DeleteMapping/:id"),
            FileSpec(f"{test}/{el}/{e}ServiceTest.java", "test",
                f"@ExtendWith(MockitoExtension). @Mock {e}Repository. @InjectMocks {e}Service. "
                f"Tests: findAll, findById success, findById throws EntityNotFoundException, create, update, delete"),
        ]

    return files


# ─── Python / FastAPI ─────────────────────────────────────────────────────────

def python_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    p = pkg  # ex: src/myapp
    files: list[FileSpec] = []

    files += [
        FileSpec(f"{p}/main.py", "bootstrap",
            "FastAPI(title=name, lifespan=lifespan). "
            "CORS middleware. Include all routers. GET /health returns {status:ok}"),
        FileSpec(f"{p}/core/config.py", "config",
            "class Settings(BaseSettings): DATABASE_URL, SECRET_KEY, ALGORITHM='HS256', "
            "ACCESS_TOKEN_EXPIRE_MINUTES=30. model_config=SettingsConfigDict(env_file='.env'). "
            "settings = Settings()"),
        FileSpec(f"{p}/core/database.py", "db",
            "async_engine = create_async_engine(settings.DATABASE_URL). "
            "AsyncSessionLocal. Base = declarative_base(). "
            "async def get_session() -> AsyncGenerator[AsyncSession]: yield session"),
        FileSpec(f"{p}/core/exceptions.py", "exception",
            "class NotFoundError(HTTPException): def __init__(detail): super().__init__(404,detail). "
            "class ConflictError(HTTPException): super().__init__(409). "
            "@app.exception_handler(NotFoundError) and global handler in main.py"),
    ]

    if has_auth:
        files += [
            FileSpec(f"{p}/auth/auth.py", "auth",
                "create_access_token(data): jwt.encode with SECRET_KEY. "
                "verify_token(token): jwt.decode. "
                "hash_password, verify_password: passlib bcrypt. "
                "get_current_user dependency: reads Bearer token, returns user"),
            FileSpec(f"{p}/auth/router.py", "router",
                "APIRouter prefix='/auth'. POST /login: OAuth2PasswordRequestForm, returns token. "
                "POST /register: creates user, returns UserResponse"),
            FileSpec(f"{p}/auth/schemas.py", "schema",
                "TokenResponse(BaseModel): access_token, token_type='bearer'. "
                "LoginRequest(BaseModel): email, password"),
        ]

    for entity in entities:
        e  = entity
        el = entity.lower()

        files += [
            FileSpec(f"{p}/{el}/models.py", "model",
                f"class {e}(Base): __tablename__='{el}s'. "
                f"id=Column(UUID, primary_key=True, default=uuid4). "
                f"domain columns. created_at=Column(DateTime, server_default=func.now()). "
                f"updated_at=Column(DateTime, onupdate=func.now())"),
            FileSpec(f"{p}/{el}/schemas.py", "schema",
                f"class {e}Base(BaseModel): domain fields with types. "
                f"class {e}Create({e}Base): pass. "
                f"class {e}Update(BaseModel): all Optional fields. "
                f"class {e}Response({e}Base): model_config=ConfigDict(from_attributes=True). id:UUID. timestamps"),
            FileSpec(f"{p}/{el}/service.py", "service",
                f"class {e}Service: inject AsyncSession. "
                f"get_all(): select({e}). get_by_id(id): raises NotFoundError. "
                f"create(data:{e}Create): db.add, commit, refresh. "
                f"update(id,data:{e}Update): get_by_id then update fields. "
                f"delete(id): get_by_id then db.delete"),
            FileSpec(f"{p}/{el}/router.py", "router",
                f"APIRouter(prefix='/{el}s', tags=['{el}s']). "
                f"GET /, GET /{{id}}, POST /, PATCH /{{id}}, DELETE /{{id}}. "
                f"Inject AsyncSession via Depends(get_session). Inject {e}Service"),
            FileSpec(f"tests/{el}/test_{el}.py", "test",
                f"pytest-asyncio. AsyncMock session. Tests: get_all, get_by_id success, "
                f"get_by_id raises NotFoundError, create, update, delete"),
        ]

    return files


# ─── .NET 8 ───────────────────────────────────────────────────────────────────

def dotnet_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    files: list[FileSpec] = []
    api = f"{name}.Api"
    inf = f"{name}.Infrastructure"
    dom = f"{name}.Domain"
    app = f"{name}.Application"

    files += [
        FileSpec(f"{api}/Program.cs", "bootstrap",
            "builder.Services.AddControllers(). AddEndpointsApiExplorer(). AddSwaggerGen(). "
            "AddDbContext<AppDbContext>(Npgsql). AddScoped repositories. "
            "app.UseSwagger/SwaggerUI. MapControllers()"),
        FileSpec(f"{inf}/AppDbContext.cs", "db",
            "AppDbContext(DbContextOptions) : DbContext. "
            f"DbSet<T> for each entity: {', '.join(entities)}. "
            "override SaveChangesAsync: sets CreatedAt/UpdatedAt"),
        FileSpec(f"{api}/Middleware/ExceptionMiddleware.cs", "middleware",
            "IMiddleware. Catches Exception, returns ProblemDetails with status/title/detail"),
    ]

    for entity in entities:
        e  = _pascal(entity)
        el = entity.lower()

        files += [
            FileSpec(f"{dom}/{e}.cs", "entity",
                f"public class {e}: Id(Guid), domain properties with getters/setters. "
                f"DateTime CreatedAt, DateTime? UpdatedAt"),
            FileSpec(f"{app}/{e}Dto.cs", "dto",
                f"public record Create{e}Request(domain fields with [Required] attributes). "
                f"public record Update{e}Request(optional domain fields). "
                f"public record {e}Response(Guid Id, fields, DateTime CreatedAt)"),
            FileSpec(f"{app}/I{e}Repository.cs", "interface",
                f"public interface I{e}Repository: "
                f"Task<IEnumerable<{e}>> GetAllAsync(). Task<{e}?> GetByIdAsync(Guid). "
                f"Task<{e}> AddAsync({e}). Task UpdateAsync({e}). Task DeleteAsync(Guid). "
                f"All with CancellationToken ct=default"),
            FileSpec(f"{inf}/Repositories/{e}Repository.cs", "repository",
                f"public class {e}Repository(AppDbContext ctx) : I{e}Repository. "
                f"EF Core CRUD: ctx.{e}s.ToListAsync(), FindAsync, Add/Update/Remove + SaveChangesAsync"),
            FileSpec(f"{app}/{e}Service.cs", "service",
                f"public class {e}Service(I{e}Repository repo). "
                f"GetAllAsync, GetByIdAsync (throws KeyNotFoundException), "
                f"CreateAsync(Create{e}Request), UpdateAsync(Guid, Update{e}Request), DeleteAsync(Guid)"),
            FileSpec(f"{api}/Controllers/{e}Controller.cs", "controller",
                f"[ApiController] [Route('api/v1/{el}s')] class {e}Controller({e}Service svc). "
                f"GET /, GET /{{id}}, POST /, PUT /{{id}}, DELETE /{{id}}. "
                f"Returns ActionResult with proper status codes"),
            FileSpec(f"{name}.Tests/{e}ServiceTests.cs", "test",
                f"class {e}ServiceTests. NSubstitute I{e}Repository. "
                f"GetByIdAsync_ReturnsItem, GetByIdAsync_ThrowsWhenNotFound, CreateAsync_Persists"),
        ]

    return files


# ─── Next.js ──────────────────────────────────────────────────────────────────

def nextjs_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    files: list[FileSpec] = [
        FileSpec("src/app/layout.tsx", "layout",
            "RootLayout with metadata, Providers(children), Tailwind globals"),
        FileSpec("src/app/page.tsx", "page",
            "Home page with navigation to feature sections"),
        FileSpec("src/lib/api.ts", "api-client",
            "axios instance baseURL=NEXT_PUBLIC_API_URL. request interceptor adds Bearer token. "
            "response interceptor: 401 → clear token redirect login"),
        FileSpec("src/components/providers.tsx", "provider",
            "'use client' QueryClientProvider(react-query) + auth state hydration"),
        FileSpec("prisma/schema.prisma", "schema",
            f"datasource db postgresql. generator client. Models: {', '.join(entities)}"
            + (' User Session Account' if has_auth else '') +
            ". Each model: id String @id @default(cuid()), createdAt DateTime @default(now()), updatedAt DateTime @updatedAt"),
    ]

    if has_auth:
        files += [
            FileSpec("src/lib/auth.ts", "auth",
                "NextAuth config: PrismaAdapter, CredentialsProvider validate email+password bcrypt. "
                "jwt callback adds user.id. session callback adds session.user.id"),
            FileSpec("src/app/api/auth/[...nextauth]/route.ts", "route",
                "export {GET,POST} = handler from lib/auth"),
            FileSpec("src/app/(auth)/login/page.tsx", "page",
                "'use client' login form. react-hook-form + zod. calls signIn('credentials')"),
        ]

    for entity in entities:
        e  = entity
        el = entity.lower()
        ep = el + "s"

        files += [
            FileSpec(f"src/lib/{el}/types.ts", "types",
                f"export type {e} = {{id:string, domain fields, createdAt:string, updatedAt:string}}. "
                f"export type Create{e}Input. export type Update{e}Input"),
            FileSpec(f"src/lib/{el}/api.ts", "api-client",
                f"{el}Api: getAll()->Promise<{e}[]>, getById(id)->Promise<{e}>, "
                f"create(data:Create{e}Input)->Promise<{e}>, update(id,data)->Promise<{e}>, delete(id)->void. "
                f"All using api from src/lib/api.ts"),
            FileSpec(f"src/hooks/use-{el}.ts", "hook",
                f"useQuery getAll with key ['{ep}']. useMutation create/update/delete with invalidateQueries. "
                f"Export: use{e}s(), use{e}(id), useCreate{e}(), useUpdate{e}(), useDelete{e}()"),
            FileSpec(f"src/app/{ep}/page.tsx", "page",
                f"Server Component. fetches {ep}, renders {e}List in Suspense"),
            FileSpec(f"src/app/{ep}/_components/{e}List.tsx", "component",
                f"'use client'. use{e}s hook. loading/error states. card grid with edit/delete"),
            FileSpec(f"src/app/{ep}/_components/{e}Form.tsx", "component",
                f"'use client'. react-hook-form + zod. create or update mode. calls mutation"),
            FileSpec(f"src/app/api/{ep}/route.ts", "route",
                f"GET (list), POST (create). Uses Prisma client. Returns NextResponse.json"),
            FileSpec(f"src/app/api/{ep}/[id]/route.ts", "route",
                f"GET, PUT, DELETE for /api/{ep}/[id]. Uses Prisma"),
        ]

    return files


# ─── Angular ─────────────────────────────────────────────────────────────────

def angular_manifest(name: str, pkg: str, entities: list[str], has_auth: bool) -> list[FileSpec]:
    files: list[FileSpec] = [
        FileSpec("src/app/app.config.ts", "config",
            "provideRouter(routes), provideHttpClient(withInterceptors([jwtInterceptor])), provideAnimations()"),
        FileSpec("src/app/app.routes.ts", "routes",
            f"lazy routes for: {', '.join(e.lower() for e in entities)}" + (", auth" if has_auth else "")),
        FileSpec("src/environments/environment.ts", "env",
            "export const environment = {production:false, apiUrl:'http://localhost:3001/api/v1'}"),
        FileSpec("src/environments/environment.prod.ts", "env",
            "export const environment = {production:true, apiUrl:'/api/v1'}"),
        FileSpec("src/app/core/http.service.ts", "service",
            "BaseHttpService(private http:HttpClient). baseUrl=environment.apiUrl. "
            "get<T>(path), post<T>(path,body), put<T>, patch<T>, delete<T>. All return Observable"),
    ]

    if has_auth:
        files += [
            FileSpec("src/app/core/auth.service.ts", "service",
                "AuthService. token=signal<string|null>(localStorage.getItem('token')). "
                "isAuthenticated=computed(()=>!!token()). "
                "login(email,pass): POST /auth/login → stores token. logout(): clears token"),
            FileSpec("src/app/core/jwt.interceptor.ts", "interceptor",
                "HttpInterceptorFn: reads token from AuthService, adds Authorization header if exists"),
            FileSpec("src/app/core/auth.guard.ts", "guard",
                "CanActivateFn: checks AuthService.isAuthenticated(). Redirects to /login if not"),
            FileSpec("src/app/features/auth/login/login.component.ts", "component",
                "Standalone LoginComponent. ReactiveFormsModule. calls AuthService.login(). navigate on success"),
        ]

    for entity in entities:
        e  = entity
        el = entity.lower()
        ep = el + "s"

        files += [
            FileSpec(f"src/app/core/models/{el}.model.ts", "model",
                f"export interface {e} {{id:string, domain fields, createdAt:string}}. "
                f"export interface Create{e}Dto. export interface Update{e}Dto"),
            FileSpec(f"src/app/core/services/{el}.service.ts", "service",
                f"{e}Service extends BaseHttpService. "
                f"items=signal<{e}[]>([]). loading=signal(false). "
                f"getAll():Observable<{e}[]>. getById(id). create(dto). update(id,dto). delete(id). "
                f"Side-effects update the signal"),
            FileSpec(f"src/app/features/{el}/{el}.routes.ts", "routes",
                f"Routes: '' (list), 'new' (create), ':id' (detail), ':id/edit' (edit). Standalone lazy"),
            FileSpec(f"src/app/features/{el}/{el}-list/{el}-list.component.ts", "component",
                f"Standalone {e}ListComponent. inject {e}Service. ngOnInit calls getAll(). "
                f"Template: *ngFor with edit/delete buttons. Loading/error states"),
            FileSpec(f"src/app/features/{el}/{el}-form/{el}-form.component.ts", "component",
                f"Standalone {e}FormComponent. ReactiveFormsModule. Create and edit modes. "
                f"Submits via {e}Service. Navigates back on success"),
        ]

    return files


# ─── Next.js (api client mode, fullstack frontend) ───────────────────────────

def nextjs_api_client_manifest(name: str, pkg: str, entities: list[str],
                                has_auth: bool, api_port: int = 3001) -> list[FileSpec]:
    files: list[FileSpec] = [
        FileSpec("src/app/layout.tsx", "layout", "Root layout with Providers, Tailwind"),
        FileSpec("src/app/page.tsx", "page", "Home with navigation to features"),
        FileSpec("src/lib/api-client.ts", "api-client",
            f"axios baseURL=NEXT_PUBLIC_API_URL (http://localhost:{api_port}/api/v1). "
            "request interceptor: adds Authorization Bearer from localStorage. "
            "response interceptor: 401 → localStorage.removeItem('token') + redirect"),
        FileSpec("src/components/providers.tsx", "provider",
            "'use client' QueryClientProvider"),
    ]

    if has_auth:
        files += [
            FileSpec("src/lib/auth-store.ts", "store",
                "zustand store: token, user, login(email,pass)→calls POST /auth/login, logout(). "
                "persist to localStorage. isAuthenticated getter"),
            FileSpec("src/middleware.ts", "middleware",
                "Next.js middleware: check token cookie, redirect unauthenticated to /login"),
            FileSpec("src/app/(auth)/login/page.tsx", "page",
                "'use client'. Login form with react-hook-form+zod. Calls authStore.login()"),
        ]

    for entity in entities:
        e  = entity
        el = entity.lower()
        ep = el + "s"

        files += [
            FileSpec(f"src/lib/{el}/types.ts", "types",
                f"{e} interface matching backend DTO. Create{e}Input, Update{e}Input"),
            FileSpec(f"src/lib/{el}/api.ts", "api-client",
                f"export const {el}Api = {{ getAll, getById, create, update, remove }} "
                f"using api-client calling /api/v1/{ep}"),
            FileSpec(f"src/hooks/use-{el}.ts", "hook",
                f"React Query hooks: use{e}s(), use{e}(id), useCreate{e}(), useUpdate{e}(), useDelete{e}(). "
                f"invalidateQueries on mutations"),
            FileSpec(f"src/app/{ep}/page.tsx", "page",
                f"Server Component with Suspense wrapping {e}ListClient"),
            FileSpec(f"src/app/{ep}/_components/{e}ListClient.tsx", "component",
                f"'use client'. use{e}s hook. Loading/error. Card/table grid. Edit/delete buttons"),
            FileSpec(f"src/app/{ep}/_components/{e}Form.tsx", "component",
                f"'use client'. react-hook-form+zod. create/edit mode. "
                f"calls useCreate{e} or useUpdate{e}"),
        ]

    return files


def angular_api_client_manifest(name: str, pkg: str, entities: list[str],
                                  has_auth: bool, api_port: int = 3001) -> list[FileSpec]:
    return angular_manifest(name, pkg, entities, has_auth)


# ─── Dispatcher ──────────────────────────────────────────────────────────────

def get_manifest(stack: str, name: str, entities: list[str], has_auth: bool,
                 api_port: int = 3001, db_type: str = "postgres", **kwargs) -> list[FileSpec]:
    kwargs["db_type"] = db_type
    pkg = _pkg(name, stack)

    # ── NestJS: roteia pelo banco detectado ───────────────────────────────
    if stack == "nestjs":
        from tools.db_strategy import get_strategy
        strat = get_strategy(db_type)
        if strat.is_nosql:
            # MongoDB, Cassandra, etc → usa manifest Mongoose
            return nestjs_mongoose_manifest(name, pkg, entities, has_auth)
        else:
            # PostgreSQL, MySQL, SQLite, MariaDB → usa manifest TypeORM
            return nestjs_manifest(name, pkg, entities, has_auth, db_type=db_type)

    # ── Outras stacks ─────────────────────────────────────────────────────
    dispatch = {
        "nestjs-mongo":    nestjs_mongoose_manifest,
        "spring-boot":     spring_boot_manifest,
        "python":          python_manifest,
        "dotnet":          dotnet_manifest,
        "nextjs":          nextjs_manifest,
        "angular":         angular_manifest,
        "nextjs-client":   lambda n, p, e, a: nextjs_api_client_manifest(n, p, e, a, api_port),
        "angular-client":  lambda n, p, e, a: angular_api_client_manifest(n, p, e, a, api_port),
    }
    fn = dispatch.get(stack)
    if not fn:
        raise ValueError(f"Stack '{stack}' sem manifest. Disponíveis: nestjs, {', '.join(dispatch)}")
    return fn(name, pkg, entities, has_auth)


def _pascal(s: str) -> str:
    return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))


def _pkg(name: str, stack: str = "") -> str:
    if stack == "spring-boot":
        return f"com.devai.{name.replace('-','').replace('_','').lower()}"
    return f"src/{name.replace('-','_').lower()}"
