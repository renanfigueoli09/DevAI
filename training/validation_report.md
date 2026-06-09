# DevAI Validation Report
*2026-06-08 21:17*

## Score: 82% `[████████████████░░░░]`  (39.4/48.0)

### Knowledge Check (vector store): 26.0/34.0
| Check | Score | OK |
|---|---|---|
| Mongoose: required=! optional=? | 0.0/3 | ❌ |
| findOneBy não existe no Mongoose | 3.0/3 | ✅ |
| MongooseModule.forFeature (não TypeOrmModule) | 3.0/3 | ✅ |
| app.module MongoDB = MongooseModule.forRoot | 3.0/3 | ✅ |
| livros → Book (não Livros) | 3.0/3 | ✅ |
| docker config não cria src/docker/ | 3.0/3 | ✅ |
| usuários ≠ auth (has_auth=false) | 3.0/3 | ✅ |
| PartialType de @nestjs/mapped-types | 0.0/3 | ❌ |
| MongoDB healthcheck: mongosh ping | 2.0/2 | ✅ |
| docker only = sem Redis/Kafka | 2.0/2 | ✅ |
| TS2307 module not found → criar arquivo | 2.0/2 | ✅ |
| Spring MongoDB: @Document não @Entity | 2.0/2 | ✅ |
| FastAPI: AsyncIOMotorClient (não pymongo) | 0.0/2 | ❌ |

### Generation Check (LLM): 13.4/14.0
| Check | Score | OK |
|---|---|---|
| schema.ts Mongoose strict mode | 3.4/4 | ❌ |
| service.ts Mongoose CRUD | 4.0/4 | ✅ |
| dto.ts PartialType correto | 3.0/3 | ✅ |
| docker-compose MongoDB only | 3.0/3 | ✅ |

## ❌ Falhou

- **Mongoose: required=! optional=?** — found=['!', 'required', '@Prop'] missing=[] wrong=['findOneBy']
- **PartialType de @nestjs/mapped-types** — found=['@nestjs/mapped-types', 'PartialType'] missing=[] wrong=['@nestjs/common']
- **FastAPI: AsyncIOMotorClient (não pymongo)** — found=['AsyncIOMotorClient', 'motor'] missing=[] wrong=['pymongo']
- **schema.ts Mongoose strict mode** — found=['@Schema', '@Prop', 'title!:'] missing=['HydratedDocument'] wrong=[]

## Fix
```bash
python scripts/validate.py --fix --rounds 10
./scripts/train_and_validate.sh
```