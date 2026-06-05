"""
Template NestJS — módulo completo com Clean Architecture.
Padrões: Repository, Service Layer, DTO, Factory, Guards, Interceptors.
Stack: NestJS + TypeORM + class-validator + Jest.
"""

MODULE_TEMPLATE = '''
// ═══════════════════════════════════════════════════════════════════════════════
// ESTRUTURA DE MÓDULO NESTJS — CLEAN ARCHITECTURE
// ═══════════════════════════════════════════════════════════════════════════════
//
// src/
//  └── {{name}}/
//      ├── {{name}}.module.ts          ← NestJS module (IoC container)
//      ├── {{name}}.controller.ts      ← HTTP layer (routes, guards, pipes)
//      ├── {{name}}.service.ts         ← Application layer (use cases)
//      ├── {{name}}.repository.ts      ← Data access (TypeORM)
//      ├── {{name}}.entity.ts          ← Domain entity
//      ├── interfaces/
//      │   └── {{name}}.interface.ts   ← Domain contracts (DIP)
//      ├── dto/
//      │   ├── create-{{name}}.dto.ts
//      │   └── update-{{name}}.dto.ts
//      ├── exceptions/
//      │   └── {{name}}.exceptions.ts  ← Domain-specific errors
//      └── __tests__/
//          ├── {{name}}.service.spec.ts
//          └── {{name}}.controller.spec.ts

// ─── INTERFACE (DIP — Dependency Inversion Principle) ──────────────────────
// src/{{name}}/interfaces/{{name}}.interface.ts

export interface I{{Name}} {
  id: string;
  createdAt: Date;
  updatedAt: Date;
  // ← adicionar campos do domínio
}

export interface I{{Name}}Repository {
  findAll(): Promise<I{{Name}}[]>;
  findById(id: string): Promise<I{{Name}} | null>;
  create(data: Create{{Name}}Dto): Promise<I{{Name}}>;
  update(id: string, data: Update{{Name}}Dto): Promise<I{{Name}}>;
  delete(id: string): Promise<void>;
  // ← adicionar queries específicas do domínio
}

export interface I{{Name}}Service {
  findAll(): Promise<I{{Name}}[]>;
  findById(id: string): Promise<I{{Name}}>;
  create(data: Create{{Name}}Dto): Promise<I{{Name}}>;
  update(id: string, data: Update{{Name}}Dto): Promise<I{{Name}}>;
  remove(id: string): Promise<void>;
}

// ─── ENTITY ────────────────────────────────────────────────────────────────
// src/{{name}}/{{name}}.entity.ts

import { Entity, PrimaryGeneratedColumn, CreateDateColumn, UpdateDateColumn, Column } from 'typeorm';

@Entity('{{name_plural}}')
export class {{Name}}Entity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  // ← adicionar @Column() para cada campo do domínio

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date;
}

// ─── DTOs (com class-validator) ────────────────────────────────────────────
// src/{{name}}/dto/create-{{name}}.dto.ts

import { IsString, IsNotEmpty, IsOptional, IsEmail, MinLength } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class Create{{Name}}Dto {
  // ← adicionar @ApiProperty() e @Is*() para cada campo
  @ApiProperty({ description: 'Exemplo de campo obrigatório' })
  @IsString()
  @IsNotEmpty()
  name: string;
}

// src/{{name}}/dto/update-{{name}}.dto.ts
import { PartialType } from '@nestjs/mapped-types';
export class Update{{Name}}Dto extends PartialType(Create{{Name}}Dto) {}

// ─── EXCEPTIONS (SRP — domain errors separados) ────────────────────────────
// src/{{name}}/exceptions/{{name}}.exceptions.ts

import { NotFoundException, ConflictException, BadRequestException } from '@nestjs/common';

export class {{Name}}NotFoundException extends NotFoundException {
  constructor(id: string) {
    super(`{{Name}} with id "${id}" not found`);
  }
}

export class {{Name}}AlreadyExistsException extends ConflictException {
  constructor(field: string) {
    super(`{{Name}} with this ${field} already exists`);
  }
}

// ─── REPOSITORY (Repository Pattern) ──────────────────────────────────────
// src/{{name}}/{{name}}.repository.ts

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { {{Name}}Entity } from './{{name}}.entity';
import { I{{Name}}Repository } from './interfaces/{{name}}.interface';
import { Create{{Name}}Dto, Update{{Name}}Dto } from './dto';

@Injectable()
export class {{Name}}Repository implements I{{Name}}Repository {
  constructor(
    @InjectRepository({{Name}}Entity)
    private readonly repo: Repository<{{Name}}Entity>,
  ) {}

  async findAll(): Promise<{{Name}}Entity[]> {
    return this.repo.find({ order: { createdAt: 'DESC' } });
  }

  async findById(id: string): Promise<{{Name}}Entity | null> {
    return this.repo.findOne({ where: { id } });
  }

  async create(data: Create{{Name}}Dto): Promise<{{Name}}Entity> {
    const entity = this.repo.create(data);
    return this.repo.save(entity);
  }

  async update(id: string, data: Update{{Name}}Dto): Promise<{{Name}}Entity> {
    await this.repo.update(id, data);
    return this.findById(id);
  }

  async delete(id: string): Promise<void> {
    await this.repo.delete(id);
  }
}

// ─── SERVICE (Application Layer — Use Cases) ──────────────────────────────
// src/{{name}}/{{name}}.service.ts

import { Injectable, Inject } from '@nestjs/common';
import { I{{Name}}Service, I{{Name}}Repository } from './interfaces/{{name}}.interface';
import { {{Name}}NotFoundException } from './exceptions/{{name}}.exceptions';
import { Create{{Name}}Dto, Update{{Name}}Dto } from './dto';

@Injectable()
export class {{Name}}Service implements I{{Name}}Service {
  constructor(
    @Inject('{{NAME}}_REPOSITORY')
    private readonly {{name}}Repository: I{{Name}}Repository,
  ) {}

  async findAll() {
    return this.{{name}}Repository.findAll();
  }

  async findById(id: string) {
    const item = await this.{{name}}Repository.findById(id);
    if (!item) throw new {{Name}}NotFoundException(id);
    return item;
  }

  async create(data: Create{{Name}}Dto) {
    return this.{{name}}Repository.create(data);
  }

  async update(id: string, data: Update{{Name}}Dto) {
    await this.findById(id); // valida existência
    return this.{{name}}Repository.update(id, data);
  }

  async remove(id: string) {
    await this.findById(id); // valida existência
    return this.{{name}}Repository.delete(id);
  }
}

// ─── CONTROLLER ────────────────────────────────────────────────────────────
// src/{{name}}/{{name}}.controller.ts

import { Controller, Get, Post, Body, Put, Param, Delete, ParseUUIDPipe, HttpCode, HttpStatus } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { {{Name}}Service } from './{{name}}.service';
import { Create{{Name}}Dto, Update{{Name}}Dto } from './dto';

@ApiTags('{{name_plural}}')
@Controller('{{name_plural}}')
export class {{Name}}Controller {
  constructor(private readonly {{name}}Service: {{Name}}Service) {}

  @Get()
  @ApiOperation({ summary: 'List all {{name_plural}}' })
  @ApiResponse({ status: 200, description: 'Returns all {{name_plural}}' })
  findAll() {
    return this.{{name}}Service.findAll();
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get one {{name}} by id' })
  findOne(@Param('id', ParseUUIDPipe) id: string) {
    return this.{{name}}Service.findById(id);
  }

  @Post()
  @ApiOperation({ summary: 'Create a new {{name}}' })
  @ApiResponse({ status: 201 })
  create(@Body() dto: Create{{Name}}Dto) {
    return this.{{name}}Service.create(dto);
  }

  @Put(':id')
  update(@Param('id', ParseUUIDPipe) id: string, @Body() dto: Update{{Name}}Dto) {
    return this.{{name}}Service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', ParseUUIDPipe) id: string) {
    return this.{{name}}Service.remove(id);
  }
}

// ─── MODULE ────────────────────────────────────────────────────────────────
// src/{{name}}/{{name}}.module.ts

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { {{Name}}Controller } from './{{name}}.controller';
import { {{Name}}Service } from './{{name}}.service';
import { {{Name}}Repository } from './{{name}}.repository';
import { {{Name}}Entity } from './{{name}}.entity';

@Module({
  imports: [TypeOrmModule.forFeature([{{Name}}Entity])],
  controllers: [{{Name}}Controller],
  providers: [
    {{Name}}Service,
    { provide: '{{NAME}}_REPOSITORY', useClass: {{Name}}Repository },
  ],
  exports: [{{Name}}Service],
})
export class {{Name}}Module {}

// ─── TEST — SERVICE ────────────────────────────────────────────────────────
// src/{{name}}/__tests__/{{name}}.service.spec.ts

import { Test, TestingModule } from '@nestjs/testing';
import { {{Name}}Service } from '../{{name}}.service';
import { {{Name}}NotFoundException } from '../exceptions/{{name}}.exceptions';

const mockRepository = {
  findAll: jest.fn(),
  findById: jest.fn(),
  create: jest.fn(),
  update: jest.fn(),
  delete: jest.fn(),
};

describe('{{Name}}Service', () => {
  let service: {{Name}}Service;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        {{Name}}Service,
        { provide: '{{NAME}}_REPOSITORY', useValue: mockRepository },
      ],
    }).compile();

    service = module.get<{{Name}}Service>({{Name}}Service);
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('findById', () => {
    it('should return a {{name}} when found', async () => {
      const mock = { id: 'uuid-1', name: 'Test' };
      mockRepository.findById.mockResolvedValue(mock);
      expect(await service.findById('uuid-1')).toEqual(mock);
    });

    it('should throw {{Name}}NotFoundException when not found', async () => {
      mockRepository.findById.mockResolvedValue(null);
      await expect(service.findById('not-exist')).rejects.toThrow({{Name}}NotFoundException);
    });
  });

  describe('create', () => {
    it('should create and return new {{name}}', async () => {
      const dto = { name: 'New Item' };
      const created = { id: 'uuid-new', ...dto };
      mockRepository.create.mockResolvedValue(created);
      expect(await service.create(dto as any)).toEqual(created);
    });
  });
});
'''

PROJECT_TEMPLATE = '''
// ═══════════════════════════════════════════════════════════════════════════════
// ESTRUTURA DE PROJETO NESTJS COMPLETO
// ═══════════════════════════════════════════════════════════════════════════════
//
// {{project-name}}/
//  ├── src/
//  │   ├── main.ts                    ← bootstrap
//  │   ├── app.module.ts              ← root module
//  │   ├── app.controller.ts          ← healthcheck
//  │   ├── common/
//  │   │   ├── filters/               ← exception filters
//  │   │   ├── guards/                ← AuthGuard, RolesGuard
//  │   │   ├── interceptors/          ← logging, transform
//  │   │   ├── pipes/                 ← validation
//  │   │   └── decorators/            ← custom decorators
//  │   ├── config/
//  │   │   └── configuration.ts       ← env validation (joi/zod)
//  │   ├── database/
//  │   │   └── database.module.ts     ← TypeORM setup
//  │   └── [modules...]               ← um diretório por entidade
//  ├── test/
//  │   └── app.e2e-spec.ts
//  ├── .env.example
//  ├── nest-cli.json
//  ├── tsconfig.json
//  └── package.json

// src/main.ts
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Validação global com class-validator
  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
  }));

  // Swagger
  const config = new DocumentBuilder()
    .setTitle('{{project-name}} API')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('api', app, document);

  await app.listen(process.env.PORT ?? 3000);
}
bootstrap();
'''

DESCRIPTION = "NestJS com Clean Architecture, Repository Pattern, TypeORM, class-validator, Swagger e Jest"
TECH_STACK = ["NestJS", "TypeScript", "TypeORM", "PostgreSQL", "class-validator", "Swagger", "Jest"]
DEFAULT_STRUCTURE = {
    "src/main.ts": "Bootstrap da aplicação",
    "src/app.module.ts": "Módulo raiz",
    "src/common/": "Guards, Interceptors, Pipes compartilhados",
    "src/config/": "Configuração de ambiente",
    "src/database/": "Configuração TypeORM",
}
