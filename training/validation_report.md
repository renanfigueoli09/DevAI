# DevAI Validation Report
*2026-06-05 23:44*

## Score: 53% `[██████████░░░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| common-errors | 6.0/6.0 | 100% | ✅ |
| nlp | 7.9/15.0 | 53% | ❌ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| fastapi | 2.0/4.0 | 50% | ❌ |
| nestjs-mongodb | 1.5/15.0 | 10% | ❌ |
| spring-mongodb | 0.0/4.0 | 0% | ❌ |

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

### nlp (53%)
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, docker-compose, Dockerfile`
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `não, no`

### spring-mongodb (0%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Wrong: `@Entity`
- ✗ Spring Data MongoDB: extends MongoRepository or JpaRepository?
  - Wrong: `JpaRepository`

### fastapi (50%)
- ✗ FastAPI: Pydantic v2 model method to serialize: model_dump or dic
  - Wrong: `.dict()`

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