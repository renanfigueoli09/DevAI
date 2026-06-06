# DevAI Validation Report
*2026-06-06 09:33*

## Score: 0% `[░░░░░░░░░░░░░░░░░░░░]`

| Tópico | Score | % | Status |
|---|---|---|---|
| nestjs-mongodb | 0.0/15.0 | 0% | ❌ |

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

## Como corrigir

```bash
# Fix automático (retreina + re-valida)
python scripts/validate.py --fix

# Forçar retreinamento específico
python scripts/validate.py --fix --topic nestjs-mongodb

# Overnight
./scripts/study.sh --group all --loop --validate --intensive
```