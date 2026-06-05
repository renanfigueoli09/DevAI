"""
Knowledge Templates — padrões extraídos do projeto de referência.

Inclui templates prontos para:
  - Docker-compose (MongoDB, Redis Sentinel, Kafka, MinIO)
  - Configurações NestJS (config.service, winston, redis.sentinels)
  - Estrutura de módulos (model + schema + service + controller + gateway + kafka)
  - Arquivos de infraestrutura (entrypoint.sh, redis-slave.conf, sentinel.conf)

Usado pelo generator e infra_generator para injetar código real e funcional.
"""

# ─── Docker-compose completo com todos os serviços ────────────────────────────

DOCKER_COMPOSE_FULL = """version: '3.8'

services:
  # ── App ──────────────────────────────────────────────────────────────────────
  app:
    build: .
    container_name: {name}-app
    depends_on:
      - mongodb
      - kafka
      - redis-sentinel-1
      - redis-sentinel-2
      - redis-sentinel-3
    entrypoint: .docker/entrypoint.sh
    ports:
      - "${{PORT}}:${{PORT}}"
    volumes:
      - .:/home/node/app
    networks:
      - api
      - redis-network
    environment:
      PORT: ${{PORT}}
      URL: "http://localhost:${{PORT}}/"
      TZ: America/Sao_Paulo
      ENV_AMB: LOCAL
      APP_VERSION: "Local"
      DBAAS_MONGODB_ENDPOINT: mongodb://mongodb:27017/
      KAFKA_BROKER: kafka:9093
      KAFKA_GROUP_ID: {name}-consumer-group
      KAFKA_CLIENT_ID: {name}-consumer-client
      DBAAS_SENTINEL_HOSTS: 'redis-sentinel-1,redis-sentinel-2,redis-sentinel-3'
      DBAAS_SENTINEL_PORT: 26379
      DBAAS_SENTINEL_SERVICE_NAME: mymaster
      DBAAS_SENTINEL_PASSWORD: redis_pass
      JWT_SECRET: ${{JWT_SECRET}}
      EXPIRES_TOKEN: 48h
{extra_env}

  # ── MongoDB ───────────────────────────────────────────────────────────────────
  mongodb:
    image: mongo:7.0
    container_name: {name}-mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongo-data:/data/db
    networks:
      - api
    command: mongod --bind_ip_all
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 15s
      timeout: 10s
      retries: 5
    restart: unless-stopped

  # ── Kafka + Zookeeper ─────────────────────────────────────────────────────────
  zookeeper:
    image: wurstmeister/zookeeper:latest
    container_name: {name}-zookeeper
    environment:
      ZOOKEEPER_SERVER_ID: 1
      ZOOKEEPER_LISTENER_PORT: 2181
    ports:
      - "2181:2181"
    networks:
      - api
    restart: unless-stopped

  kafka:
    image: wurstmeister/kafka:latest
    container_name: {name}-kafka
    environment:
      KAFKA_ADVERTISED_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INSIDE:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INSIDE
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: 'true'
    ports:
      - "9093:9093"
    networks:
      - api
    depends_on:
      - zookeeper
    restart: unless-stopped

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    container_name: {name}-kafka-ui
    ports:
      - "8080:8080"
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9093
      KAFKA_CLUSTERS_0_ZOOKEEPER: zookeeper:2181
    depends_on:
      - kafka
    networks:
      - api
    restart: unless-stopped

  # ── Redis Sentinel (master + slave + 3 sentinels) ─────────────────────────────
  redis-master:
    image: redis:7-alpine
    container_name: {name}-redis-master
    command: ["redis-server", "--requirepass", "redis_pass"]
    networks:
      redis-network:
        ipv4_address: 172.30.0.3
    restart: unless-stopped

  redis-slave:
    image: redis:7-alpine
    container_name: {name}-redis-slave
    command: ["redis-server", "/usr/local/etc/redis/redis-slave.conf"]
    depends_on:
      - redis-master
    volumes:
      - ./redis/redis-slave.conf:/usr/local/etc/redis/redis-slave.conf
    networks:
      redis-network:
        ipv4_address: 172.30.0.4
    restart: unless-stopped

  redis-sentinel-1:
    image: redis:7
    container_name: {name}-redis-sentinel-1
    volumes:
      - ./redis/sentinel.conf:/etc/redis/sentinel.conf
    command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
    ports:
      - "26379:26379"
    networks:
      redis-network:
        ipv4_address: 172.30.0.5
    depends_on:
      - redis-master
    restart: unless-stopped

  redis-sentinel-2:
    image: redis:7
    container_name: {name}-redis-sentinel-2
    volumes:
      - ./redis/sentinel.conf:/etc/redis/sentinel.conf
    command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
    ports:
      - "26380:26379"
    networks:
      redis-network:
        ipv4_address: 172.30.0.6
    depends_on:
      - redis-master
    restart: unless-stopped

  redis-sentinel-3:
    image: redis:7
    container_name: {name}-redis-sentinel-3
    volumes:
      - ./redis/sentinel.conf:/etc/redis/sentinel.conf
    command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
    ports:
      - "26381:26379"
    networks:
      redis-network:
        ipv4_address: 172.30.0.7
    depends_on:
      - redis-master
    restart: unless-stopped
{minio_service}

volumes:
  mongo-data:
{extra_volumes}

networks:
  redis-network:
    ipam:
      config:
        - subnet: 172.30.0.0/16
  api:
    driver: bridge
"""

MINIO_SERVICE = """
  # ── MinIO (S3-compatible object storage) ──────────────────────────────────────
  minio:
    image: minio/minio:latest
    container_name: {name}-minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    command: server /data --console-address ":9001"
    volumes:
      - minio-data:/data
    networks:
      - api
    restart: unless-stopped
"""

DOCKER_COMPOSE_DEV = """version: '3.8'
# Desenvolvimento: só infra (DB + Cache + Queue). App roda no host com hot-reload.
services:
  mongodb:
    image: mongo:7.0
    container_name: {name}-mongodb-dev
    ports:
      - "27017:27017"
    command: mongod --bind_ip_all
    networks:
      - {name}-dev

  redis-master:
    image: redis:7-alpine
    container_name: {name}-redis-master-dev
    command: ["redis-server", "--requirepass", "redis_pass"]
    networks:
      {name}-dev-redis:
        ipv4_address: 172.31.0.3

  redis-slave:
    image: redis:7-alpine
    container_name: {name}-redis-slave-dev
    command: ["redis-server", "/usr/local/etc/redis/redis-slave.conf"]
    depends_on:
      - redis-master
    volumes:
      - ./redis/redis-slave.conf:/usr/local/etc/redis/redis-slave.conf
    networks:
      {name}-dev-redis:
        ipv4_address: 172.31.0.4

  redis-sentinel:
    image: redis:7
    container_name: {name}-redis-sentinel-dev
    volumes:
      - ./redis/sentinel.conf:/etc/redis/sentinel.conf
    command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
    ports:
      - "26379:26379"
    networks:
      {name}-dev-redis:
        ipv4_address: 172.31.0.5
    depends_on:
      - redis-master

  zookeeper:
    image: wurstmeister/zookeeper:latest
    container_name: {name}-zookeeper-dev
    ports:
      - "2181:2181"
    networks:
      - {name}-dev

  kafka:
    image: wurstmeister/kafka:latest
    container_name: {name}-kafka-dev
    environment:
      KAFKA_ADVERTISED_LISTENERS: INSIDE://localhost:9093
      KAFKA_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INSIDE:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INSIDE
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    ports:
      - "9093:9093"
    networks:
      - {name}-dev
    depends_on:
      - zookeeper

networks:
  {name}-dev:
    driver: bridge
  {name}-dev-redis:
    ipam:
      config:
        - subnet: 172.31.0.0/16
"""

# ─── Redis config files ────────────────────────────────────────────────────────

REDIS_SLAVE_CONF = """# Redis Slave Configuration
port 6379
bind 0.0.0.0
dir /data
logfile ""
replicaof redis-master 6379
masterauth "redis_pass"
dbfilename slave-dump.rdb
appendonly no
timeout 0
loglevel notice
"""

REDIS_SENTINEL_CONF = """# Redis Sentinel Configuration
port 26379
dir /tmp

sentinel monitor mymaster 172.30.0.3 6379 2
sentinel auth-pass mymaster redis_pass
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
sentinel parallel-syncs mymaster 4
"""

# ─── NestJS Dockerfile ────────────────────────────────────────────────────────

DOCKERFILE_NESTJS = """FROM node:22-alpine AS builder
WORKDIR /home/node/app
COPY package*.json ./
RUN npm install --legacy-peer-deps --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /home/node/app
COPY --from=builder /home/node/app/dist ./dist
COPY --from=builder /home/node/app/node_modules ./node_modules
COPY --from=builder /home/node/app/package.json ./
COPY .docker/ ./.docker/
RUN chmod +x .docker/entrypoint.sh
ENV NODE_ENV=production
EXPOSE ${PORT:-3000}
CMD [".docker/entrypoint.sh"]
"""

ENTRYPOINT_SH = """#!/bin/bash
set -e

echo "→ Aguardando serviços..."
sleep 5

echo "→ Iniciando aplicação (produção)..."
exec node dist/main
"""

ENTRYPOINT_SH_DOCKER = """#!/bin/bash
set -e

# Aguarda o banco estar pronto
echo "→ Aguardando banco de dados..."
sleep 8

# Verifica se o build existe
if [ ! -f "dist/main.js" ]; then
  echo "→ Build não encontrado — compilando..."
  npm run build
fi

echo "→ Iniciando servidor..."
exec node dist/main
"""

ENTRYPOINT_SH_DEV = """#!/bin/bash
set -e

echo "→ Instalando dependências..."
npm install --legacy-peer-deps

echo "→ Iniciando em modo desenvolvimento (hot-reload)..."
exec npm run start:dev
"""

# ─── NestJS Config files ──────────────────────────────────────────────────────

CONFIG_SERVICE_TS = """import { ConfigService } from '@nestjs/config';

export const configService = new ConfigService();
"""

REDIS_SENTINELS_CONFIG_TS = """import { configService } from './config.service';

export const redisSentinelsConfig = {
  name: configService.get<string>('DBAAS_SENTINEL_SERVICE_NAME') || 'mymaster',
  sentinels: (configService.get<string>('DBAAS_SENTINEL_HOSTS') || 'localhost')
    .split(',')
    .map((host) => ({
      host: host.trim(),
      port: +(configService.get<number>('DBAAS_SENTINEL_PORT') || 26379),
    })),
  password: configService.get<string>('DBAAS_SENTINEL_PASSWORD') || 'redis_pass',
};
"""

WINSTON_CONFIG_TS = (
    "import {{ WinstonModuleOptions, utilities }} from 'nest-winston';\n"
    "import * as winston from 'winston';\n"
    "import {{ configService }} from './config.service';\n"
    "\n"
    "export default {{\n"
    "  level: configService.get<string>('ENV_AMB') === 'LOCAL' ? 'debug' : 'info',\n"
    "  transports: [\n"
    "    new winston.transports.Console({{\n"
    "      format: winston.format.combine(\n"
    "        winston.format.timestamp(),\n"
    "        winston.format.ms(),\n"
    "        utilities.format.nestLike('{name}', {{\n"
    "          colors: true,\n"
    "          prettyPrint: true,\n"
    "        }}),\n"
    "      ),\n"
    "    }}),\n"
    "  ],\n"
    "}} as WinstonModuleOptions;\n"
)

APP_MODULE_FULL_TS = (
    "import {{ Module }} from '@nestjs/common';\n"
    "import {{ ConfigModule }} from '@nestjs/config';\n"
    "import {{ MongooseModule }} from '@nestjs/mongoose';\n"
    "import {{ CacheModule }} from '@nestjs/cache-manager';\n"
    "import {{ JwtModule }} from '@nestjs/jwt';\n"
    "import {{ BullModule }} from '@nestjs/bull';\n"
    "import {{ WinstonModule }} from 'nest-winston';\n"
    "import {{ configService }} from './configs/config.service';\n"
    "import winstonConfig from './configs/winston.config';\n"
    "import {{ redisSentinelsConfig }} from './configs/redis.sentinels.config';\n"
    "import {{ redisStore }} from 'cache-manager-redis-store';\n"
    "{module_imports}\n"
    "\n"
    "@Module({{\n"
    "  imports: [\n"
    "    ConfigModule.forRoot({{ isGlobal: true, envFilePath: '.env' }}),\n"
    "    MongooseModule.forRoot(\n"
    "      configService.get<string>('DBAAS_MONGODB_ENDPOINT') || 'mongodb://localhost:27017/',\n"
    "      {{ dbName: '{db_name}' }},\n"
    "    ),\n"
    "    CacheModule.registerAsync({{\n"
    "      isGlobal: true,\n"
    "      useFactory: () => ({{ store: redisStore, ...redisSentinelsConfig }}),\n"
    "    }}),\n"
    "    WinstonModule.forRoot(winstonConfig),\n"
    "    JwtModule.register({{\n"
    "      global: true,\n"
    "      secret: configService.get<string>('JWT_SECRET') || 'secret',\n"
    "      signOptions: {{ expiresIn: configService.get<string>('EXPIRES_TOKEN') || '48h' }},\n"
    "    }}),\n"
    "    BullModule.forRoot({{ redis: redisSentinelsConfig }}),\n"
    "    {module_list}\n"
    "  ],\n"
    "}})\n"
    "export class AppModule {{}}\n"
)


MONGOOSE_SCHEMA_EXAMPLE = """
// schemas/{entity}.schema.ts — SchemaFactory + HydratedDocument
import {{ SchemaFactory }} from '@nestjs/mongoose';
import {{ {Entity} }} from './{entity}.schema.model';
import {{ HydratedDocument }} from 'mongoose';

export const {Entity}_schema = SchemaFactory.createForClass({Entity});
export type {Entity}Document = HydratedDocument<{Entity}>;
"""

# Model with @Schema + @Prop — non-null assertion (!) for required, ? for optional
MONGOOSE_MODEL_EXAMPLE = """
// {entity}.schema.ts — @Schema class with TypeScript strict mode
// REQUIRED fields: use @Prop({{ required: true }}) and type!: Type (non-null assertion)
// OPTIONAL fields: use @Prop() and type?: Type (no !)
import {{ Prop, Schema, SchemaFactory }} from '@nestjs/mongoose';
import {{ ApiProperty, ApiPropertyOptional }} from '@nestjs/swagger';
import {{ IsString, IsNotEmpty, IsEmail, IsOptional }} from 'class-validator';
import {{ HydratedDocument }} from 'mongoose';

export type {Entity}Document = HydratedDocument<{Entity}>;

@Schema({{ timestamps: true }})
export class {Entity} {{
  @ApiProperty()
  @Prop({{ required: true, index: true }})
  @IsString() @IsNotEmpty()
  name!: string;  // ! = required, non-null assertion (TypeScript strict mode)

  @ApiPropertyOptional()
  @Prop()
  @IsString() @IsOptional()
  description?: string;  // ? = optional (no !)
}}

export const {Entity}Schema = SchemaFactory.createForClass({Entity});
"""

KAFKA_PRODUCER_EXAMPLE = """
// services/{entity}.producer.service.ts — Kafka producer pattern
import {{ Inject, Injectable, OnModuleDestroy, OnModuleInit }} from '@nestjs/common';
import {{ ClientKafka }} from '@nestjs/microservices';
import {{ Observable }} from 'rxjs';

@Injectable()
export class {Entity}ProducerService implements OnModuleInit, OnModuleDestroy {{
  constructor(@Inject('{ENTITY}_MODULE') private readonly client: ClientKafka) {{}}

  async onModuleInit() {{
    this.client.subscribeToResponseOf('{entity}.create');
    this.client.subscribeToResponseOf('{entity}.update');
    this.client.subscribeToResponseOf('{entity}.delete');
    await this.client.connect();
  }}

  async onModuleDestroy() {{
    await this.client.close();
  }}

  sendMessage<T>(topic: string, message: T): Observable<T> {{
    return this.client.emit<T>(topic, message);
  }}
}}
"""

WEBSOCKET_GATEWAY_EXAMPLE = """
// gateway/{entity}.gateway.ts — WebSocket Gateway pattern
import {{ Logger }} from '@nestjs/common';
import {{
  WebSocketGateway, SubscribeMessage, MessageBody,
  OnGatewayConnection, OnGatewayDisconnect, WebSocketServer, ConnectedSocket,
}} from '@nestjs/websockets';
import {{ Server, WebSocket }} from 'ws';
import {{ JwtService }} from '@nestjs/jwt';
import {{ {Entity}Service }} from '../services/{entity}.service';

@WebSocketGateway({{ transports: ['websocket'], cors: {{ origin: '*' }} }})
export class {Entity}Gateway implements OnGatewayConnection, OnGatewayDisconnect {{
  @WebSocketServer() server!: Server;
  private readonly logger = new Logger({Entity}Gateway.name);

  constructor(
    private readonly {entity}Service: {Entity}Service,
    private readonly jwtService: JwtService,
  ) {{}}

  async handleConnection(client: WebSocket, req: any) {{
    const url = new URL(req.url, 'http://localhost');
    const token = url.searchParams.get('token');
    try {{
      if (!token) return client.close(1008, 'token required');
      this.jwtService.verify(token);
    }} catch {{
      return client.close(1008, 'Unauthorized');
    }}
    this.logger.log('Client connected');
  }}

  handleDisconnect(client: WebSocket) {{
    this.logger.log('Client disconnected');
  }}

  @SubscribeMessage('{entity}.getAll')
  async getAll(@MessageBody() body: {{ page?: number; limit?: number }}) {{
    try {{
      const result = await this.{entity}Service.findAll();
      return {{ event: '{entity}.getAll', data: result }};
    }} catch (error: any) {{
      return {{ event: 'error', data: error?.response ?? error }};
    }}
  }}
}}
"""

BULL_PROCESSOR_EXAMPLE = """
// jobs/{entity}.processor.service.ts — Bull job processor pattern
import {{ Injectable, Logger }} from '@nestjs/common';
import {{ InjectQueue, Process, Processor }} from '@nestjs/bull';
import {{ Job, Queue }} from 'bull';

@Processor('{entity}.process')
export class {Entity}ProcessorService {{
  private readonly logger = new Logger({Entity}ProcessorService.name);

  constructor(
    @InjectQueue('{entity}.process') private readonly queue: Queue,
  ) {{}}

  @Process({{ name: '{entity}.job', concurrency: 1 }})
  async process{Entity}(job: Job<any>): Promise<string> {{
    this.logger.log(`Processing job ${{job.id}}: {entity}.job`);
    const {{ data }} = job;
    // Process the job data here
    this.logger.log(`Job ${{job.id}} completed`);
    return 'completed';
  }}
}}
"""

# ─── Package lists ────────────────────────────────────────────────────────────

# Todos os pacotes do projeto de referência que o DevAI deve instalar
REFERENCE_PACKAGES = [
    "@nestjs/bull", "bull", "@bull-board/api", "@bull-board/express",
    "@nestjs/microservices", "kafkajs",
    "ioredis", "cache-manager-redis-store", "cache-manager-ioredis-yet", "cache-manager",
    "@nestjs/cache-manager",
    "@nestjs/platform-ws", "@nestjs/websockets", "ws",
    "@nestjs/platform-socket.io", "socket.io",
    "nest-winston", "winston",
    "@nestjs/swagger",
    "@nestjs/jwt", "passport-jwt",
    "@nestjs/mongoose", "mongoose",
    "@nestjs/config",
    "@nestjs/mapped-types",
    "class-validator", "class-transformer",
    "bcryptjs", "reflect-metadata", "rxjs",
]

REFERENCE_DEV_PACKAGES = [
    "@nestjs/testing", "@types/ws", "@types/node",
    "@types/jest", "jest", "ts-jest", "supertest", "@types/supertest",
    "tsconfig-paths", "ts-node", "typescript",
]

# ─── tsconfig.json com path aliases ──────────────────────────────────────────

TSCONFIG_JSON = """{
  "compilerOptions": {
    "module": "commonjs",
    "declaration": true,
    "removeComments": true,
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "allowSyntheticDefaultImports": true,
    "target": "ES2023",
    "sourceMap": true,
    "outDir": "./dist",
    "baseUrl": "./",
    "incremental": true,
    "skipLibCheck": true,
    "strictNullChecks": false,
    "noImplicitAny": false,
    "resolveJsonModule": true,
    "paths": {
      "@config/*": ["src/configs/*"],
      "@common/*": ["src/modules/common/*"],
      "@auth/*": ["src/modules/auth/*"]
    }
  }
}
"""

# ─── .env.example completo ────────────────────────────────────────────────────

ENV_EXAMPLE_FULL = """PORT=3000
ENV_AMB=LOCAL
APP_VERSION=1.0.0

# MongoDB
DBAAS_MONGODB_ENDPOINT=mongodb://localhost:27017/

# Redis Sentinel
DBAAS_SENTINEL_HOSTS=localhost,localhost,localhost
DBAAS_SENTINEL_PORT=26379
DBAAS_SENTINEL_SERVICE_NAME=mymaster
DBAAS_SENTINEL_PASSWORD=redis_pass

# Kafka
KAFKA_BROKER=localhost:9093
KAFKA_GROUP_ID={name}-consumer-group
KAFKA_CLIENT_ID={name}-consumer-client

# Auth
JWT_SECRET=change-me-in-production
EXPIRES_TOKEN=48h

# S3/MinIO (opcional)
# AWS_ENDPOINT=http://localhost:9000/
# AWS_ACCESS_KEY_ID=minioadmin
# AWS_SECRET_ACCESS_KEY=minioadmin123
# REGIONAWS=us-east-1
"""

MAIN_TS_FULL = (
    "import {{ NestFactory }} from '@nestjs/core';\n"
    "import {{ AppModule }} from './app.module';\n"
    "import {{ configService }} from './configs/config.service';\n"
    "import {{ WINSTON_MODULE_NEST_PROVIDER }} from 'nest-winston';\n"
    "import {{ DocumentBuilder, SwaggerModule }} from '@nestjs/swagger';\n"
    "import {{ Logger, ValidationPipe }} from '@nestjs/common';\n"
    "import {{ MicroserviceOptions, Transport }} from '@nestjs/microservices';\n"
    "import {{ WsAdapter }} from '@nestjs/platform-ws';\n"
    "\n"
    "async function bootstrap() {{\n"
    "  const logger = new Logger();\n"
    "  const app = await NestFactory.create(AppModule);\n"
    "  app.useWebSocketAdapter(new WsAdapter(app));\n"
    "  app.enableCors();\n"
    "  app.useLogger(app.get(WINSTON_MODULE_NEST_PROVIDER));\n"
    "  app.setGlobalPrefix('/api');\n"
    "  app.useGlobalPipes(new ValidationPipe({{ whitelist: true, transform: true }}));\n"
    "  const swaggerConfig = new DocumentBuilder()\n"
    "    .setTitle('{name} API').setDescription('{description}')\n"
    "    .setVersion('1.0').addBearerAuth().build();\n"
    "  SwaggerModule.setup('swagger', app,\n"
    "    SwaggerModule.createDocument(app, swaggerConfig),\n"
    "    {{ swaggerOptions: {{ persistAuthorization: true }} }});\n"
    "  app.connectMicroservice<MicroserviceOptions>({{\n"
    "    transport: Transport.KAFKA,\n"
    "    options: {{ client: {{ brokers: [configService.get<string>('KAFKA_BROKER') || 'localhost:9093'] }},\n"
    "      consumer: {{ groupId: '{name}-group', allowAutoTopicCreation: true }} }},\n"
    "  }});\n"
    "  await app.startAllMicroservices();\n"
    "  const port = configService.get<number>('PORT') || 3000;\n"
    "  await app.listen(port);\n"
    "  logger.log('Server running on port ' + port);\n"
    "}}\n"
    "bootstrap().catch((err) => {{ new Logger().error('Boot error', err); process.exit(1); }});\n"
)
