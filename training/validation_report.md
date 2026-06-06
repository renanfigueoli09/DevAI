# DevAI Validation Report
*2026-06-06 07:08*

## Score: 54% `[██████████░░░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| nlp | 8.5/15.0 | 56% | ❌ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| fastapi | 2.0/4.0 | 50% | ❌ |
| common-errors | 3.0/6.0 | 50% | ❌ |
| nestjs-mongodb | 4.5/15.0 | 30% | ❌ |
| spring-mongodb | 0.0/4.0 | 0% | ❌ |

## ❌ Retreinar urgente

### nestjs-mongodb (30%)
- ✗ NestJS Mongoose: required field uses ! or ? TypeScript modifier?
  - Wrong: `?`
- ✗ NestJS Mongoose service: which method to use instead of findOneBy
  - Missing: `findById`
  - Wrong: `findOneBy`
- ✗ NestJS Mongoose module: which import to use, MongooseModule.forFe
  - Wrong: `TypeOrmModule`

### nestjs-typeorm (50%)
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Wrong: `@InjectModel`

### nlp (56%)
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never`
  - Wrong: `src/docker, src/mongodb`

### spring-mongodb (0%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Wrong: `@Entity`
- ✗ Spring Data MongoDB: extends MongoRepository or JpaRepository?
  - Wrong: `JpaRepository`

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
python scripts/validate.py --fix --topic nlp

# Overnight
./scripts/study.sh --group all --loop --validate --intensive
```