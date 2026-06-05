"""
Generator — gera cada arquivo individualmente com um prompt focado.
A chave da confiabilidade: um arquivo por chamada LLM, prompt + template curto e direto.
"""

import json
import re
from pathlib import Path
from tools.code_fixer import fix_all, is_valid_content, preinstall_nestjs_deps
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from config import MODEL_CODE, VERBOSE
from tools.manifests import FileSpec

console = Console()

# ── Templates inline por tipo de arquivo ──────────────────────────────────────
# Estes são "esqueletos reais" que o LLM vê como referência.
# Curtos o suficiente para caber no contexto (< 600 tokens cada).

# ─── NestJS working code snippets (LLM uses as direct reference) ─────────────
# These are proven, compilable TypeScript. LLM should follow EXACTLY.

NESTJS_DTO_EXAMPLE = """
// DTO file example — import PartialType from @nestjs/mapped-types ONLY
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsNotEmpty, IsNumber, IsOptional, IsEmail, MinLength, Min } from 'class-validator';
import { PartialType } from '@nestjs/mapped-types';  // MUST be @nestjs/mapped-types, NOT @nestjs/common

export class CreateProductDto {
  @ApiProperty({ description: 'Product name' })
  @IsString() @IsNotEmpty()
  name: string;

  @ApiProperty({ description: 'Price in cents' })
  @IsNumber() @Min(0)
  price: number;

  @ApiPropertyOptional()
  @IsString() @IsOptional()
  description?: string;
}

export class UpdateProductDto extends PartialType(CreateProductDto) {}
"""

NESTJS_SERVICE_EXAMPLE = """
// Service file — uses Repository<Entity> directly (no wrapper), correct TypeORM pattern
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DeepPartial } from 'typeorm';
import { ProductEntity } from './product.entity';
import { CreateProductDto, UpdateProductDto } from './product.dto';

@Injectable()
export class ProductService {
  constructor(
    @InjectRepository(ProductEntity)
    private readonly repo: Repository<ProductEntity>,
  ) {}

  findAll(): Promise<ProductEntity[]> {
    return this.repo.find({ order: { createdAt: 'DESC' } });
  }

  async findOne(id: string): Promise<ProductEntity> {
    const entity = await this.repo.findOneBy({ id });
    if (!entity) throw new NotFoundException(`Product ${id} not found`);
    return entity;
  }

  async create(dto: CreateProductDto): Promise<ProductEntity> {
    const entity = this.repo.create(dto as DeepPartial<ProductEntity>);
    return this.repo.save(entity);
  }

  async update(id: string, dto: UpdateProductDto): Promise<ProductEntity> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    return this.repo.save(entity);
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.repo.remove(entity);
  }
}
"""

NESTJS_CONTROLLER_EXAMPLE = """
// Controller — correct imports, uses findOne (not findById), correct guard path
import { Controller, Get, Post, Body, Patch, Param, Delete, UseGuards, HttpCode, HttpStatus } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { ProductService } from './product.service';
import { CreateProductDto, UpdateProductDto } from './product.dto';
import { JwtAuthGuard } from '../auth/jwt.guard';  // CORRECT path: ../auth/jwt.guard

@ApiTags('products')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('products')
export class ProductController {
  constructor(private readonly productService: ProductService) {}

  @Get() @ApiOperation({ summary: 'Get all products' })
  findAll() { return this.productService.findAll(); }

  @Get(':id')
  findOne(@Param('id') id: string) { return this.productService.findOne(id); }

  @Post() @ApiOperation({ summary: 'Create product' })
  create(@Body() dto: CreateProductDto) { return this.productService.create(dto); }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateProductDto) {
    return this.productService.update(id, dto);
  }

  @Delete(':id') @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id') id: string) { return this.productService.remove(id); }
}
"""

NESTJS_MODULE_EXAMPLE = """
// Module — ALL imports are relative to the SAME directory (./)
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ProductEntity } from './product.entity';     // ./ same dir
import { ProductService } from './product.service';   // ./ same dir
import { ProductController } from './product.controller'; // ./ same dir

@Module({
  imports: [TypeOrmModule.forFeature([ProductEntity])],
  providers: [ProductService],
  controllers: [ProductController],
  exports: [ProductService],
})
export class ProductModule {}
"""

NESTJS_SPEC_EXAMPLE = """
// Test file — uses findOne (not findById), uses getRepositoryToken, correct mock
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { NotFoundException } from '@nestjs/common';
import { ProductService } from './product.service';
import { ProductEntity } from './product.entity';

const mockRepo = {
  find: jest.fn(),
  findOneBy: jest.fn(),
  create: jest.fn(),
  save: jest.fn(),
  remove: jest.fn(),
};

describe('ProductService', () => {
  let service: ProductService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ProductService,
        { provide: getRepositoryToken(ProductEntity), useValue: mockRepo },
      ],
    }).compile();
    service = module.get<ProductService>(ProductService);
    jest.clearAllMocks();
  });

  it('findAll returns array', async () => {
    mockRepo.find.mockResolvedValue([]);
    expect(await service.findAll()).toEqual([]);
  });

  it('findOne throws NotFoundException when entity not found', async () => {
    mockRepo.findOneBy.mockResolvedValue(null);
    await expect(service.findOne('bad-id')).rejects.toThrow(NotFoundException);
  });

  it('create persists entity', async () => {
    const dto = { name: 'Test', price: 100 };
    const entity = { id: 'uuid', ...dto };
    mockRepo.create.mockReturnValue(entity);
    mockRepo.save.mockResolvedValue(entity);
    expect(await service.create(dto as any)).toEqual(entity);
  });
});
"""


# ─── MongoDB/Mongoose working examples ────────────────────────────────────────

MONGOOSE_SCHEMA_EXAMPLE = """
// Mongoose schema — uses @nestjs/mongoose, NOT typeorm
import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document, Types } from 'mongoose';

export type ProductDocument = Product & Document;

@Schema({ timestamps: true })
export class Product {
  @Prop({ required: true })
  name: string;

  @Prop({ required: true, min: 0 })
  price: number;

  @Prop()
  description?: string;
}

export const ProductSchema = SchemaFactory.createForClass(Product);
"""

MONGOOSE_SERVICE_EXAMPLE = """
// Mongoose service — uses InjectModel and Model<Document>
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Product, ProductDocument } from './product.schema';
import { CreateProductDto, UpdateProductDto } from './product.dto';

@Injectable()
export class ProductService {
  constructor(
    @InjectModel(Product.name)
    private readonly model: Model<ProductDocument>,
  ) {}

  findAll(): Promise<ProductDocument[]> {
    return this.model.find().sort({ createdAt: -1 }).exec();
  }

  async findOne(id: string): Promise<ProductDocument> {
    const doc = await this.model.findById(id).exec();
    if (!doc) throw new NotFoundException(`Product ${id} not found`);
    return doc;
  }

  create(dto: CreateProductDto): Promise<ProductDocument> {
    return new this.model(dto).save();
  }

  async update(id: string, dto: UpdateProductDto): Promise<ProductDocument> {
    const doc = await this.model
      .findByIdAndUpdate(id, { $set: dto }, { new: true })
      .exec();
    if (!doc) throw new NotFoundException(`Product ${id} not found`);
    return doc;
  }

  async remove(id: string): Promise<void> {
    const doc = await this.model.findByIdAndDelete(id).exec();
    if (!doc) throw new NotFoundException(`Product ${id} not found`);
  }
}
"""

MONGOOSE_MODULE_EXAMPLE = """
// Mongoose module — uses MongooseModule.forFeature NOT TypeOrmModule
import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { Product, ProductSchema } from './product.schema';
import { ProductService } from './product.service';
import { ProductController } from './product.controller';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: Product.name, schema: ProductSchema }]),
  ],
  providers: [ProductService],
  controllers: [ProductController],
  exports: [ProductService],
})
export class ProductModule {}
"""

MONGOOSE_SPEC_EXAMPLE = """
// Mongoose test — mock Model with getModelToken
import { Test, TestingModule } from '@nestjs/testing';
import { getModelToken } from '@nestjs/mongoose';
import { NotFoundException } from '@nestjs/common';
import { ProductService } from './product.service';
import { Product } from './product.schema';

const mockDoc = { _id: 'id123', name: 'Test', price: 100, save: jest.fn() };
const mockModel = {
  find: jest.fn().mockReturnThis(),
  findById: jest.fn().mockReturnThis(),
  findByIdAndUpdate: jest.fn().mockReturnThis(),
  findByIdAndDelete: jest.fn().mockReturnThis(),
  sort: jest.fn().mockReturnThis(),
  exec: jest.fn(),
};

// Override constructor for new this.model(dto).save()
function MockModel(dto: any) { return { ...dto, save: jest.fn().mockResolvedValue({...dto, _id: 'id123'}) }; }
Object.assign(MockModel, mockModel);

describe('ProductService (Mongoose)', () => {
  let service: ProductService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ProductService,
        { provide: getModelToken(Product.name), useValue: MockModel },
      ],
    }).compile();
    service = module.get<ProductService>(ProductService);
    jest.clearAllMocks();
  });

  it('findAll returns docs', async () => {
    mockModel.exec.mockResolvedValue([mockDoc]);
    expect(await service.findAll()).toHaveLength(1);
  });

  it('findOne throws NotFoundException when not found', async () => {
    mockModel.exec.mockResolvedValue(null);
    await expect(service.findOne('bad')).rejects.toThrow(NotFoundException);
  });
});
"""


_TEMPLATES: dict[str, str] = {

"nestjs:entity": """
import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn } from 'typeorm';

@Entity('products')
export class ProductEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ length: 255 })
  name: string;

  @Column({ type: 'decimal', precision: 10, scale: 2, default: 0 })
  price: number;

  @Column({ nullable: true })
  description: string;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;
}""",

"nestjs:service": """
import { Injectable, Inject } from '@nestjs/common';
import { IProductRepository } from './interfaces/product.interface';
import { ProductNotFoundException } from './exceptions/product.exceptions';
import { CreateProductDto, UpdateProductDto } from './product.dto';

@Injectable()
export class ProductService {
  constructor(
    @Inject('PRODUCT_REPOSITORY')
    private readonly repo: IProductRepository,
  ) {}

  findAll() { return this.repo.findAll(); }

  async findById(id: string) {
    const item = await this.repo.findById(id);
    if (!item) throw new ProductNotFoundException(id);
    return item;
  }

  create(dto: CreateProductDto) { return this.repo.create(dto); }

  async update(id: string, dto: UpdateProductDto) {
    await this.findById(id);
    return this.repo.update(id, dto);
  }

  async remove(id: string) {
    await this.findById(id);
    return this.repo.delete(id);
  }
}""",

"nestjs:controller": """
import { Controller, Get, Post, Body, Patch, Param, Delete, HttpCode, HttpStatus, UseGuards } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth, ApiCreatedResponse } from '@nestjs/swagger';
import { ProductService } from './product.service';
import { CreateProductDto, UpdateProductDto } from './product.dto';
import { JwtAuthGuard } from '../auth/jwt.guard';

@ApiTags('products')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('products')
export class ProductController {
  constructor(private readonly productService: ProductService) {}

  @Get()  @ApiOperation({ summary: 'List all' })
  findAll() { return this.productService.findAll(); }

  @Get(':id')
  findOne(@Param('id', ParseUUIDPipe) id: string) { return this.productService.findById(id); }

  @Post()
  create(@Body() dto: CreateProductDto) { return this.productService.create(dto); }

  @Put(':id')
  update(@Param('id', ParseUUIDPipe) id: string, @Body() dto: UpdateProductDto) { return this.productService.update(id, dto); }

  @Delete(':id') @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', ParseUUIDPipe) id: string) { return this.productService.remove(id); }
}""",

"nestjs:dto": """
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsNotEmpty, IsNumber, IsOptional, IsEmail, Min, IsPositive } from 'class-validator';
import { PartialType } from '@nestjs/mapped-types';

export class CreateProductDto {
  @ApiProperty({ description: 'Product name' })
  @IsString()
  @IsNotEmpty()
  name: string;

  @ApiProperty({ description: 'Product price' })
  @IsNumber()
  @IsPositive()
  price: number;

  @ApiPropertyOptional()
  @IsString()
  @IsOptional()
  description?: string;
}

export class UpdateProductDto extends PartialType(CreateProductDto) {}
""",

"nestjs:module": """
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ProductEntity } from './product.entity';
import { ProductService } from './product.service';
import { ProductController } from './product.controller';

@Module({
  imports: [TypeOrmModule.forFeature([ProductEntity])],
  providers: [ProductService],
  controllers: [ProductController],
  exports: [ProductService],
})
export class ProductModule {}
""",

"nestjs:test": """
import { Test, TestingModule } from '@nestjs/testing';
import { ProductService } from '../product.service';
import { ProductNotFoundException } from '../exceptions/product.exceptions';

const mockRepo = { findAll: jest.fn(), findById: jest.fn(), create: jest.fn(), update: jest.fn(), delete: jest.fn() };

describe('ProductService', () => {
  let service: ProductService;
  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [ProductService, { provide: 'PRODUCT_REPOSITORY', useValue: mockRepo }],
    }).compile();
    service = module.get<ProductService>(ProductService);
    jest.clearAllMocks();
  });

  it('should throw ProductNotFoundException when not found', async () => {
    mockRepo.findById.mockResolvedValue(null);
    await expect(service.findById('bad-id')).rejects.toThrow(ProductNotFoundException);
  });

  it('should create a product', async () => {
    const dto = { name: 'Test', price: 10 };
    mockRepo.create.mockResolvedValue({ id: 'uuid', ...dto });
    expect(await service.create(dto as any)).toMatchObject(dto);
  });
});""",

"spring-boot:entity": """
@Entity @Table(name = "products")
@Getter @Setter @Builder @NoArgsConstructor @AllArgsConstructor
public class ProductEntity extends AuditableEntity {
    @Id @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
    @Column(nullable = false, length = 255) private String name;
    @Column(precision = 10, scale = 2)      private BigDecimal price;
    @Column(columnDefinition = "TEXT")      private String description;
}""",

"spring-boot:service-impl": """
@Service @RequiredArgsConstructor @Transactional(readOnly = true)
public class ProductServiceImpl implements ProductService {
    private final ProductRepository repository;
    private final ProductMapper mapper;

    public List<ProductResponseDTO> findAll() {
        return repository.findAll().stream().map(mapper::toResponse).toList();
    }
    public ProductResponseDTO findById(UUID id) {
        return repository.findById(id).map(mapper::toResponse)
            .orElseThrow(() -> new EntityNotFoundException("Product not found: " + id));
    }
    @Transactional
    public ProductResponseDTO create(ProductRequestDTO dto) {
        return mapper.toResponse(repository.save(mapper.toEntity(dto)));
    }
    @Transactional
    public ProductResponseDTO update(UUID id, ProductRequestDTO dto) {
        ProductEntity e = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Product not found: " + id));
        mapper.updateEntity(dto, e);
        return mapper.toResponse(repository.save(e));
    }
    @Transactional
    public void delete(UUID id) {
        if (!repository.existsById(id)) throw new EntityNotFoundException("Product not found: " + id);
        repository.deleteById(id);
    }
}""",

"spring-boot:test": """
@ExtendWith(MockitoExtension.class)
class ProductServiceTest {
    @Mock ProductRepository repository;
    @Mock ProductMapper mapper;
    @InjectMocks ProductServiceImpl service;

    @Test void shouldThrowWhenNotFound() {
        when(repository.findById(any())).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.findById(UUID.randomUUID()))
            .isInstanceOf(EntityNotFoundException.class);
    }
    @Test void shouldCreate() {
        var dto = new ProductRequestDTO("Test", BigDecimal.TEN);
        var entity = ProductEntity.builder().id(UUID.randomUUID()).name("Test").build();
        var response = new ProductResponseDTO(entity.getId(), "Test", BigDecimal.TEN, null, null);
        when(mapper.toEntity(dto)).thenReturn(entity);
        when(repository.save(entity)).thenReturn(entity);
        when(mapper.toResponse(entity)).thenReturn(response);
        assertThat(service.create(dto).name()).isEqualTo("Test");
    }
}""",

"python:service": """
from uuid import UUID
from .interfaces import IProductRepository
from .schemas import ProductCreate, ProductUpdate
from src.core.exceptions import NotFoundError

class ProductService:
    def __init__(self, repository: IProductRepository):
        self.repository = repository

    async def find_all(self): return await self.repository.find_all()

    async def find_by_id(self, id: UUID):
        item = await self.repository.find_by_id(id)
        if not item: raise NotFoundError(f"Product {id} not found")
        return item

    async def create(self, data: ProductCreate):
        return await self.repository.create(data.model_dump())

    async def update(self, id: UUID, data: ProductUpdate):
        await self.find_by_id(id)
        return await self.repository.update(id, data.model_dump(exclude_unset=True))

    async def delete(self, id: UUID):
        await self.find_by_id(id)
        await self.repository.delete(id)""",

"python:test": """
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from src.product.service import ProductService
from src.product.schemas import ProductCreate
from src.core.exceptions import NotFoundError

@pytest.fixture
def mock_repo(): return AsyncMock()

@pytest.fixture
def service(mock_repo): return ProductService(mock_repo)

@pytest.mark.asyncio
async def test_find_by_id_not_found(service, mock_repo):
    mock_repo.find_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await service.find_by_id(uuid4())

@pytest.mark.asyncio
async def test_create(service, mock_repo):
    mock_repo.create.return_value = type('P', (), {'id': uuid4(), 'name': 'X'})()
    result = await service.create(ProductCreate(name='X'))
    mock_repo.create.assert_called_once()""",

"dotnet:entity": """
public sealed class Product {
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Name { get; private set; } = default!;
    public decimal Price { get; private set; }
    public string? Description { get; private set; }
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; private set; }

    private Product() {}

    public static Product Create(string name, decimal price, string? description = null) {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentOutOfRangeException.ThrowIfNegative(price);
        return new Product { Name = name, Price = price, Description = description };
    }

    public void Update(string? name, decimal? price, string? description) {
        if (name is not null) Name = name;
        if (price is not null) Price = price.Value;
        if (description is not null) Description = description;
        UpdatedAt = DateTime.UtcNow;
    }
}""",

"dotnet:test": """
public class ProductServiceTests {
    private readonly IProductRepository _repo = Substitute.For<IProductRepository>();
    private readonly ProductService _sut;
    public ProductServiceTests() => _sut = new ProductService(_repo);

    [Fact]
    public async Task GetByIdAsync_ThrowsWhenNotFound() {
        _repo.GetByIdAsync(Arg.Any<Guid>()).Returns((Product?)null);
        await Assert.ThrowsAsync<ProductNotFoundException>(() => _sut.GetByIdAsync(Guid.NewGuid()));
    }

    [Fact]
    public async Task CreateAsync_ReturnsCreated() {
        var req = new CreateProductRequest("Test", 9.99m);
        _repo.AddAsync(Arg.Any<Product>()).Returns(x => x.ArgAt<Product>(0));
        var result = await _sut.CreateAsync(req);
        Assert.Equal("Test", result.Name);
    }
}""",
}


def _get_template(stack: str, file_type: str) -> str:
    """Retorna o template mais próximo para o tipo de arquivo."""
    key = f"{stack}:{file_type}"
    if key in _TEMPLATES:
        return _TEMPLATES[key]
    # Tenta fallbacks por tipo genérico
    for k in _TEMPLATES:
        if k.endswith(f":{file_type}"):
            return _TEMPLATES[k]
    return ""


def generate_files(
    specs: list[FileSpec],
    stack: str,
    name: str,
    description: str,
    domain: dict,
    llm,
    output_path: Path,
) -> list[dict]:
    """
    Gera todos os arquivos do manifest, um por chamada LLM.
    Retorna lista de {"path": ..., "content": ...}.
    """
    generated = []
    entities = domain.get("entities", [])
    has_auth = domain.get("has_auth", False)

    # Contexto compartilhado (pequeno, para todos os arquivos)
    shared_ctx = (
        f"Project: {name}\n"
        f"Stack: {stack}\n"
        f"Description: {description}\n"
        f"Domain entities: {', '.join(entities)}\n"
        f"Has auth/JWT: {has_auth}\n"
    )

    # Busca versões atuais da stack (com cache 24h)
    version_ctx = ""
    try:
        from tools.web_research import fetch_stack_versions, versions_to_context
        # Normaliza stack para busca (nextjs-client → nextjs)
        base_stack = stack.replace("-client", "")
        versions = fetch_stack_versions(base_stack)
        version_ctx = versions_to_context(versions, base_stack)
        if versions:
            console.print(f"  [dim]✓ {len(versions)} versão(ões) de pacote carregada(s) do cache/web[/dim]")
    except Exception as e:
        console.print(f"  [dim]⚠ Versões offline: {e}[/dim]")

    console.print(f"\n[cyan]📝 Gerando {len(specs)} arquivo(s)...[/cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Gerando arquivos...", total=len(specs))

        for i, spec in enumerate(specs, 1):
            progress.update(task, description=f"[cyan]{spec.path}[/cyan]", advance=0)

            template = _get_template(stack, spec.file_type)
            entity_ctx = f"Entity: {spec.entity}\n" if spec.entity else ""

            # Inject proven working code examples based on file type and ORM
            working_example = ""
            is_mongo = (stack in ("nestjs-mongo",) or
                        domain.get("orm") == "mongoose" or
                        domain.get("db_type") == "mongodb")

            if stack in ("nestjs", "nestjs-mongo"):
                ft     = spec.file_type
                entity = spec.entity or "Product"
                elow   = entity.lower()

                if is_mongo:
                    # MongoDB/Mongoose examples
                    if ft in ("schema", "entity"):
                        try:
                            working_example = MONGOOSE_MODEL_EXAMPLE.replace("{Entity}", entity).replace("{entity}", elow)
                        except Exception:
                            working_example = MONGOOSE_SCHEMA_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "service":
                        working_example = MONGOOSE_SERVICE_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "module":
                        working_example = MONGOOSE_MODULE_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft in ("test", "spec"):
                        working_example = MONGOOSE_SPEC_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "dto":
                        working_example = NESTJS_DTO_EXAMPLE.replace("Product", entity).replace("product", elow)
                else:
                    # TypeORM/SQL examples
                    if ft == "dto":
                        working_example = NESTJS_DTO_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "service":
                        working_example = NESTJS_SERVICE_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "controller":
                        working_example = NESTJS_CONTROLLER_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft == "module":
                        working_example = NESTJS_MODULE_EXAMPLE.replace("Product", entity).replace("product", elow)
                    elif ft in ("test", "spec"):
                        working_example = NESTJS_SPEC_EXAMPLE.replace("Product", entity).replace("product", elow)

            # Contexto dos últimos arquivos gerados (para imports)
            recent = ""
            if generated:
                recent_files = generated[-4:]
                recent = "Already created files (use for correct imports):\n"
                recent += "\n".join(f"  - {f['path']}" for f in recent_files) + "\n"

            template_section = f"REFERENCE TEMPLATE (follow this structure exactly):\n```\n{template}\n```\n" if template else ""

            version_section = f"{version_ctx}\n\n" if version_ctx else ""
            example_section = (
                f"WORKING REFERENCE CODE (follow this EXACTLY for structure, imports, and patterns):\n"
                f"```typescript\n{working_example}\n```\n\n"
            ) if working_example else ""

            # ── Vector store: busca padrão mais relevante no training (OBRIGATÓRIO) ──
            training_ref = ""
            training_found = False
            try:
                from tools.vector_store import search_relevant
                _excl = ["docker","devops","kubernetes","github-actions","nginx","gitlab","cicd"]
                _ent  = entity or (spec.entity if spec.entity else "")
                _db   = db_type or ""
                _ft   = spec.file_type or ""
                _query = f"{stack} {_db} {_ft} {_ent}".strip()
                _training = search_relevant(_query, limit=3, exclude_topics=_excl)
                if _training and len(_training) > 80:
                    # Remove header lines, keep code content
                    _lines = [l for l in _training.split("\n")
                              if not l.startswith("===") and not l.startswith("[search:")]
                    training_ref = "\n".join(_lines[:30]).strip()
                    training_found = True
                    console.print(f"  [dim]✓ Training: {len(training_ref)} chars para {_ft or _ent}[/dim]")
                else:
                    console.print(f"  [dim]○ Training vazio para: {_query[:40]}[/dim]")
            except Exception as _te:
                console.print(f"  [dim]⚠ Training error: {_te}[/dim]")

            training_section = (
                f"=== TRAINING REFERENCE (adapt for {entity or spec.entity or 'this entity'}) ===\n"
                f"{training_ref}\n\n"
            ) if training_ref else ""

            prompt = f"""{shared_ctx}{entity_ctx}
{version_section}FILE: {spec.path}
PURPOSE: {spec.description}

{training_section}{example_section}{recent}{template_section}
CRITICAL RULES (non-negotiable):
- PartialType MUST come from '@nestjs/mapped-types' (never @nestjs/common or @nestjs/swagger)
- Import DTO from './{spec.entity.lower() if spec.entity else "entity"}.dto' (NOT from './dto')
- Service uses @InjectRepository(Entity) directly — no wrapper repository class
- repo.create(dto as DeepPartial<Entity>) — always cast to avoid TypeORM overload errors
- Module imports: ALL from './' same directory (not '../')
- Guard import: from '../auth/jwt.guard' (not from '../auth/guards/jwt-auth.guard')
- Method name: findOne (not findById)
- ONLY generate what is described — do NOT add Redis, Kafka, Bull, WebSockets, Sentinel unless explicitly asked
- If description says "Books CRUD MongoDB" → generate ONLY files for the Book entity
- Keep it minimal and focused on exactly what was asked
- TYPESCRIPT STRICT MODE: required class properties use ! (e.g. name!: string), optional use ? (e.g. email?: string)
- In Mongoose @Schema classes: @Prop({{required:true}}) → field!: Type (with !), @Prop() → field?: Type (with ?)
- NEVER write: name: string (without ! or ?) for class properties — TypeScript strict mode requires one or the other
- FILE CONTENT ONLY — the output is ONLY the file source code, no explanations, no folder names, no directory structure
- NEVER create folder names or directory paths in the output — just the file content
- DO NOT reference docker, containers, images, CI/CD, or infrastructure in TypeScript source files
- The file path is already defined — just write the code inside that file

Write the COMPLETE content of "{spec.path}".
- Real, working code. No placeholders, no TODOs, no "// implement here".
- All imports must be present and correct.
- Follow the reference template structure adapted for this entity/domain.

Return ONLY a JSON object (no markdown around it):
{{"path": "{spec.path}", "content": "full file content with \\n for newlines"}}"""

            system = (
                "You write production-ready source code.\n"
                "Return ONLY a raw JSON: {\"path\": \"...\", \"content\": \"...\"}\n"
                "RULES:\n"
                "- PartialType: ALWAYS from '@nestjs/mapped-types', never @nestjs/common\n"
                "- class-validator (IsString,IsEmail,etc): from 'class-validator'\n"
                "- TypeORM create: use 'this.repo.create(dto as any)' not 'this.repo.create(dto)'\n"
                "- DTO imports: use './entity.dto' not './dto'\n"
                "- JwtAuthGuard: from '../auth/jwt.guard' not 'guards/jwt-auth.guard'\n"
                "- Service method: findOne(id) not findById(id)\n"
                "- Module: import entity from './entity.entity' (same dir)\n"
                "No markdown, no ``` around the JSON."
            )

            resp = llm.chat(
                model=MODEL_CODE,
                messages=[{"role": "user", "content": prompt}],
                system=system,
                stream=False,  # sem stream para ser mais rápido em modo batch
            )

            file_obj = _parse_file_response(resp, spec.path)
            content_ok = (
                file_obj and
                len(file_obj.get("content", "").strip()) > 30 and
                is_valid_content(file_obj.get("content",""), spec.path)[0]
            )
            if content_ok:
                generated.append(file_obj)
                lines = len(file_obj["content"].splitlines())
                progress.update(task, description=f"[green]✓[/green] {spec.path} ({lines} linhas)", advance=1)
            else:
                # Retry com prompt mais simples
                retry = (
                    f"Write ONLY the content of {spec.path} for a {stack} project.\n"
                    f"Purpose: {spec.description}\n"
                    f"Entity: {spec.entity or 'N/A'}\n"
                    f"Return JSON: {{\"path\": \"{spec.path}\", \"content\": \"code here\"}}"
                )
                resp2 = llm.chat(
                    model=MODEL_CODE,
                    messages=[{"role": "user", "content": retry}],
                    system=system,
                    stream=False,
                )
                file_obj2 = _parse_file_response(resp2, spec.path)
                content_ok2 = (
                    file_obj2 and
                    len(file_obj2.get("content", "").strip()) > 30 and
                    is_valid_content(file_obj2.get("content",""), spec.path)[0]
                )
                if content_ok2:
                    generated.append(file_obj2)
                    progress.update(task, description=f"[yellow]~[/yellow] {spec.path} (retry)", advance=1)
                else:
                    progress.update(task, description=f"[red]✗[/red] {spec.path}", advance=1)

    ok = len(generated)
    fail = len(specs) - ok
    console.print(f"\n[green]✓ {ok} arquivo(s) gerado(s)[/green]" + (f" [yellow]· {fail} falhou(ram)[/yellow]" if fail else ""))

    # Aplica correções determinísticas (imports, barrels, conteúdo lixo)
    console.print("[dim]→ Aplicando correções automáticas...[/dim]")
    generated = fix_all(generated, stack)

    return generated


def _parse_file_response(resp: str, expected_path: str) -> dict | None:
    """Parse JSON de resposta de arquivo único, tolerante a variações."""
    text = resp.strip()

    # Remove fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip())

    # Tenta o JSON diretamente
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "path" in data and "content" in data:
            return data
    except Exception:
        pass

    # Procura JSON dentro do texto
    for m in re.finditer(r'\{', text):
        for end in range(len(text), m.start(), -1):
            if text[end-1] == '}':
                try:
                    data = json.loads(text[m.start():end])
                    if isinstance(data, dict) and "content" in data:
                        if "path" not in data:
                            data["path"] = expected_path
                        return data
                except Exception:
                    continue

    # Fallback: se a resposta parece código, usa direto
    if len(text) > 50 and not text.startswith("{"):
        # Remove possível label "FILE: path" no início
        text = re.sub(r"^FILE:\s*.+\n", "", text).strip()
        if len(text) > 50:
            return {"path": expected_path, "content": text}

    return None


# ─── Templates frontend ───────────────────────────────────────────────────────

_TEMPLATES.update({

"nextjs:api-client": """
// src/lib/api-client.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default apiClient;""",

"nextjs:api-module": """
// src/lib/product/api.ts
import apiClient from '../api-client';
import type { Product, CreateProductInput, UpdateProductInput } from './types';

export const productApi = {
  getAll: ()                          => apiClient.get<Product[]>('/products').then(r => r.data),
  getById: (id: string)              => apiClient.get<Product>(`/products/${id}`).then(r => r.data),
  create: (dto: CreateProductInput)  => apiClient.post<Product>('/products', dto).then(r => r.data),
  update: (id: string, dto: UpdateProductInput) => apiClient.put<Product>(`/products/${id}`, dto).then(r => r.data),
  remove: (id: string)               => apiClient.delete(`/products/${id}`),
};""",

"nextjs:hook": """
// src/hooks/use-products.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { productApi } from '@/lib/product/api';
import type { CreateProductInput, UpdateProductInput } from '@/lib/product/types';

const KEYS = { all: ['products'] as const, one: (id: string) => ['products', id] as const };

export function useProducts() {
  return useQuery({ queryKey: KEYS.all, queryFn: productApi.getAll });
}

export function useProduct(id: string) {
  return useQuery({ queryKey: KEYS.one(id), queryFn: () => productApi.getById(id), enabled: !!id });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dto: CreateProductInput) => productApi.create(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.all }),
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateProductInput }) => productApi.update(id, dto),
    onSuccess: (_, { id }) => { qc.invalidateQueries({ queryKey: KEYS.all }); qc.invalidateQueries({ queryKey: KEYS.one(id) }); },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => productApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.all }),
  });
}""",

"nextjs:store": """
// src/lib/auth-store.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi } from './auth-api';

interface AuthState {
  token: string | null;
  user: { id: string; name: string; email: string } | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      login: async (email, password) => {
        const { token, user } = await authApi.login(email, password);
        set({ token, user, isAuthenticated: true });
      },
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    { name: 'auth-storage' }
  )
);""",

"nextjs:component": """
// src/app/products/_components/ProductListClient.tsx
'use client';
import { useProducts, useDeleteProduct } from '@/hooks/use-products';
import type { Product } from '@/lib/product/types';

export default function ProductListClient() {
  const { data: products, isLoading, error } = useProducts();
  const deleteMutation = useDeleteProduct();

  if (isLoading) return <div className="flex justify-center p-8"><div className="animate-spin h-8 w-8 border-4 border-blue-500 rounded-full border-t-transparent" /></div>;
  if (error)    return <div className="text-red-500 p-4">Erro ao carregar produtos.</div>;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {products?.map((product: Product) => (
        <div key={product.id} className="border rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
          <h3 className="font-semibold text-lg">{product.name}</h3>
          <p className="text-gray-500 text-sm mt-1">{product.description}</p>
          <div className="flex justify-between items-center mt-4">
            <span className="font-bold text-blue-600">R$ {product.price}</span>
            <button onClick={() => deleteMutation.mutate(product.id)} className="text-red-500 hover:text-red-700 text-sm">Remover</button>
          </div>
        </div>
      ))}
    </div>
  );
}""",

"angular:service": """
// src/app/core/services/product.service.ts
import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import type { Product, CreateProductDto } from '../models/product.model';

@Injectable({ providedIn: 'root' })
export class ProductService {
  private http = inject(HttpClient);
  private url = `${environment.apiUrl}/products`;

  private _items  = signal<Product[]>([]);
  private _loading = signal(false);

  readonly items   = this._items.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly count   = computed(() => this._items().length);

  getAll(): Observable<Product[]> {
    this._loading.set(true);
    return this.http.get<Product[]>(this.url).pipe(
      tap({ next: d => { this._items.set(d); this._loading.set(false); }, error: () => this._loading.set(false) })
    );
  }
  getById(id: string): Observable<Product>  { return this.http.get<Product>(`${this.url}/${id}`); }
  create(dto: CreateProductDto): Observable<Product> { return this.http.post<Product>(this.url, dto).pipe(tap(() => this.getAll().subscribe())); }
  update(id: string, dto: Partial<CreateProductDto>): Observable<Product> { return this.http.put<Product>(`${this.url}/${id}`, dto).pipe(tap(() => this.getAll().subscribe())); }
  delete(id: string): Observable<void> { return this.http.delete<void>(`${this.url}/${id}`).pipe(tap(() => this._items.update(items => items.filter(i => i.id !== id)))); }
}""",

"angular:component": """
// src/app/features/product/product-list/product-list.component.ts
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { ProductService } from '../../../core/services/product.service';

@Component({
  selector: 'app-product-list',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <div class="container mx-auto p-4">
      <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold">Produtos</h1>
        <a routerLink="new" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Novo</a>
      </div>
      <div *ngIf="service.loading()" class="text-center py-8">Carregando...</div>
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div *ngFor="let item of service.items()" class="border rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold">{{ item.name }}</h3>
          <p class="text-gray-500 text-sm">{{ item.description }}</p>
          <div class="flex justify-between mt-3">
            <span class="font-bold text-blue-600">R$ {{ item.price }}</span>
            <button (click)="delete(item.id)" class="text-red-500 text-sm hover:text-red-700">Remover</button>
          </div>
        </div>
      </div>
    </div>
  `
})
export class ProductListComponent implements OnInit {
  protected service = inject(ProductService);
  ngOnInit() { this.service.getAll().subscribe(); }
  delete(id: string) { if (confirm('Remover?')) this.service.delete(id).subscribe(); }
}""",

"angular:interceptor": """
// src/app/core/interceptors/jwt.interceptor.ts
import { HttpInterceptorFn, HttpRequest, HttpHandlerFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

export const jwtInterceptor: HttpInterceptorFn = (req: HttpRequest<unknown>, next: HttpHandlerFn) => {
  const auth = inject(AuthService);
  const token = auth.token();
  if (token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req);
};""",

})
