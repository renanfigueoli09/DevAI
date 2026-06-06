# DevAI Validation Report
*2026-06-05 21:14*

## Score: 63% `[████████████░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| fastapi | 4.0/4.0 | 100% | ✅ |
| common-errors | 6.0/6.0 | 100% | ✅ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| nlp | 7.1/15.0 | 48% | ❌ |
| nestjs-mongodb | 6.0/15.0 | 40% | ❌ |
| spring-mongodb | 0.0/4.0 | 0% | ❌ |

## ❌ Retreinar urgente

### nestjs-mongodb (40%)
- ✗ NestJS Mongoose: required field uses ! or ? TypeScript modifier?
  - Wrong: `?`
- ✗ NestJS Mongoose schema: @Prop({required:true}) maps to field!:str
  - Wrong: `field?`
- ✗ NestJS Mongoose service: which method to use instead of findOneBy
  - Wrong: `findOneBy`

### nestjs-typeorm (50%)
- ✗ NestJS TypeORM service: @InjectRepository vs @InjectModel?
  - Wrong: `@InjectModel`

### nlp (48%)
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, Dockerfile`
  - Wrong: `src/docker`
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `não, no`

### spring-mongodb (0%)
- ✗ Spring Boot MongoDB: @Document or @Entity for model class?
  - Wrong: `@Entity`
- ✗ Spring Data MongoDB: extends MongoRepository or JpaRepository?
  - Wrong: `JpaRepository`

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