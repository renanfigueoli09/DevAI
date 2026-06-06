# DevAI Validation Report
*2026-06-06 13:21*

## Score: 61% `[████████████░░░░░░░░]`  (29.4/48.0)

### Knowledge Check (vector store): 16.0/34.0
| Check | Score | OK |
|---|---|---|
| Mongoose: required=! optional=? | 0.0/3 | ❌ |
| findOneBy não existe no Mongoose | 3.0/3 | ✅ |
| MongooseModule.forFeature (não TypeOrmModule) | 0.0/3 | ❌ |
| app.module MongoDB = MongooseModule.forRoot | 0.0/3 | ❌ |
| livros → Book (não Livros) | 3.0/3 | ✅ |
| docker config não cria src/docker/ | 3.0/3 | ✅ |
| usuários ≠ auth (has_auth=false) | 3.0/3 | ✅ |
| PartialType de @nestjs/mapped-types | 0.0/3 | ❌ |
| MongoDB healthcheck: mongosh ping | 0.0/2 | ❌ |
| docker only = sem Redis/Kafka | 2.0/2 | ✅ |
| TS2307 module not found → criar arquivo | 2.0/2 | ✅ |
| Spring MongoDB: @Document não @Entity | 0.0/2 | ❌ |
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
- **MongooseModule.forFeature (não TypeOrmModule)** — found=['MongooseModule.forFeature', 'BookSchema'] missing=[] wrong=['TypeOrmModule.forFeature']
- **app.module MongoDB = MongooseModule.forRoot** — found=['MongooseModule.forRoot', 'MONGODB_URI'] missing=[] wrong=['DB_HOST', 'TypeOrmModule']
- **PartialType de @nestjs/mapped-types** — found=['@nestjs/mapped-types', 'PartialType'] missing=[] wrong=['@nestjs/common']
- **MongoDB healthcheck: mongosh ping** — found=['mongosh', 'ping'] missing=[] wrong=['pg_isready']
- **Spring MongoDB: @Document não @Entity** — found=['@Document', 'MongoRepository'] missing=[] wrong=['@Entity', 'JpaRepository']
- **FastAPI: AsyncIOMotorClient (não pymongo)** — found=['AsyncIOMotorClient', 'motor'] missing=[] wrong=['MongoClient', 'pymongo']
- **schema.ts Mongoose strict mode** — found=['@Schema', '@Prop', 'title!:'] missing=['HydratedDocument'] wrong=[]

## Fix
```bash
python scripts/validate.py --fix --rounds 10
./scripts/train_and_validate.sh
```