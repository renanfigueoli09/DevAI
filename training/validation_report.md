# DevAI Validation Report
*2026-06-06 05:53*

## Score: 39% `[███████░░░░░░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| spring-mongodb | 2.0/4.0 | 50% | ❌ |
| fastapi | 2.0/4.0 | 50% | ❌ |
| common-errors | 3.0/6.0 | 50% | ❌ |
| nestjs-auth | 2.0/5.0 | 40% | ❌ |
| nlp | 3.1/15.0 | 21% | ❌ |
| nestjs-mongodb | 1.5/15.0 | 10% | ❌ |

## ❌ Retreinar urgente

### nestjs-mongodb (10%)
- ✗ NestJS Mongoose: required field uses ! or ? TypeScript modifier?
  - Wrong: `?`
- ✗ NestJS Mongoose schema: @Prop({required:true}) maps to field!:str
  - Wrong: `field?`
- ✗ NestJS Mongoose service: which method to use instead of findOneBy
  - Missing: `findById`
  - Wrong: `findOneBy`
- ✗ NestJS Mongoose module: which import to use, MongooseModule.forFe
  - Wrong: `TypeOrmModule`

### nestjs-typeorm (50%)
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Wrong: `@InjectModel`

### nestjs-auth (40%)
- ✗ NestJS PartialType: from @nestjs/mapped-types or @nestjs/common?
  - Wrong: `@nestjs/common`

### nlp (21%)
- ✗ User says 'CRUD de livros com MongoDB'. What is the entity name?
  - Wrong: `Livros, livros, LIVROS, Livro`
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, Dockerfile`
  - Wrong: `src/docker, src/mongodb`
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `não, no`

### spring-mongodb (50%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Wrong: `@Entity`

### fastapi (50%)
- ✗ FastAPI: Pydantic v2 model method to serialize: model_dump or dic
  - Wrong: `.dict()`

### common-errors (50%)
- ✗ NestJS error: PartialType from @nestjs/common — what is correct i
  - Wrong: `@nestjs/common`

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