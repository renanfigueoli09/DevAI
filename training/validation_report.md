# DevAI Validation Report
*2026-06-05 21:43*

## Score: 66% `[█████████████░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| common-errors | 6.0/6.0 | 100% | ✅ |
| nestjs-mongodb | 9.0/15.0 | 60% | ⚠️ |
| nlp | 8.5/15.0 | 56% | ❌ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| fastapi | 2.0/4.0 | 50% | ❌ |
| spring-mongodb | 0.0/4.0 | 0% | ❌ |

## ❌ Retreinar urgente

### nestjs-typeorm (50%)
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Wrong: `@InjectModel`

### nlp (56%)
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, Dockerfile`
  - Wrong: `src/docker`

### spring-mongodb (0%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Wrong: `@Entity, @Table`
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
python scripts/validate.py --fix --topic nestjs-typeorm
python scripts/validate.py --fix --topic nlp
python scripts/validate.py --fix --topic spring-mongodb

# Overnight
./scripts/study.sh --group all --loop --validate --intensive
```