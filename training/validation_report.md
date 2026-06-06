# DevAI Validation Report
*2026-06-05 22:55*

## Score: 62% `[████████████░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| nlp | 8.2/15.0 | 55% | ❌ |
| nestjs-mongodb | 7.5/15.0 | 50% | ❌ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| spring-mongodb | 2.0/4.0 | 50% | ❌ |
| fastapi | 2.0/4.0 | 50% | ❌ |
| common-errors | 3.0/6.0 | 50% | ❌ |

## ❌ Retreinar urgente

### nestjs-mongodb (50%)
- ✗ NestJS Mongoose: required field uses ! or ? TypeScript modifier?
  - Wrong: `?`
- ✗ NestJS Mongoose service: which method to use instead of findOneBy
  - Missing: `findById`
  - Wrong: `findOneBy`

### nestjs-typeorm (50%)
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Wrong: `@InjectModel`

### nlp (55%)
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `não`
  - Wrong: `JWT`

### spring-mongodb (50%)
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