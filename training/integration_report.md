# DevAI Integration Test Report
*2026-06-08 20:44*

## Score: 62% `[████████████░░░░░░░░]`

| Test | Score | Status |
|---|---|---|
| nestjs-mongodb-basic | 5.0/5.0 (100%) | ✅ |
| nestjs-mongodb-no-auth | 3.0/4.0 (75%) | ⚠️ |
| nestjs-mongodb-docker | 0.0/2.0 (0%) | ❌ |
| nestjs-redis-sentinel | 1.0/2.0 (50%) | ⚠️ |
| nestjs-postgres-auth | 1.0/3.0 (33%) | ❌ |

## ❌ Falhas Detalhadas

### nestjs-mongodb-no-auth
- **.env.example**
  - Wrong:   `JWT_SECRET, JWT_EXPIRES`
### nestjs-mongodb-docker
- **docker-compose.yml**
  - File not found: docker-compose.yml
- **Dockerfile**
  - File not found: Dockerfile
### nestjs-redis-sentinel
- **docker-compose.yml**
  - File not found: docker-compose.yml
### nestjs-postgres-auth
- **src/user/user.entity.ts**
  - File not found: src/user/user.entity.ts
- **src/user/user.service.ts**
  - File not found: src/user/user.service.ts

## Fix
```bash
python scripts/integration_test.py --fix
python scripts/validate.py --fix --loop
```