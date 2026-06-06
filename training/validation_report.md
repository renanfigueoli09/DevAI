# DevAI Validation Report
*2026-06-05 22:05*

## Score: 67% `[█████████████░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-auth | 5.0/5.0 | 100% | ✅ |
| nestjs-core | 4.0/4.0 | 100% | ✅ |
| docker | 4.0/4.0 | 100% | ✅ |
| spring-mongodb | 4.0/4.0 | 100% | ✅ |
| fastapi | 4.0/4.0 | 100% | ✅ |
| common-errors | 6.0/6.0 | 100% | ✅ |
| nestjs-typeorm | 2.0/4.0 | 50% | ❌ |
| nestjs-mongodb | 6.0/15.0 | 40% | ❌ |
| nlp | 5.8/15.0 | 39% | ❌ |

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

### nlp (39%)
- ✗ User says 'configure docker com mongodb'. Should you create src/d
  - Missing: `não, never, Dockerfile`
  - Wrong: `src/docker`
- ✗ User says 'API de usuários com MongoDB'. Is has_auth true or fals
  - Missing: `não`
  - Wrong: `JWT`

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