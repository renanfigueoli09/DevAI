"""
Template .NET 8 — Minimal API + Clean Architecture.
Padrões: Repository, CQRS lite, FluentValidation, xUnit.
"""

MODULE_TEMPLATE = '''
// ═══════════════════════════════════════════════════════════════════════════════
// ESTRUTURA DE MÓDULO .NET 8 — CLEAN ARCHITECTURE
// ═══════════════════════════════════════════════════════════════════════════════
//
// src/
//  ├── {{Name}}.Api/               ← Presentation (Minimal API)
//  ├── {{Name}}.Application/       ← Use Cases, DTOs, Interfaces
//  ├── {{Name}}.Domain/            ← Entities, Exceptions, Enums
//  └── {{Name}}.Infrastructure/   ← Repository, EF Core, External

// ─── Domain/{{Name}}Entity.cs ───────────────────────────────────────────────
namespace {{Name}}.Domain.Entities;

public class {{Name}}Entity
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    // ← propriedades do domínio
    public string Name { get; private set; } = default!;
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; private set; }

    private {{Name}}Entity() { }  // EF Core

    public static {{Name}}Entity Create(string name)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        return new {{Name}}Entity { Name = name };
    }

    public void Update(string? name)
    {
        if (name is not null) Name = name;
        UpdatedAt = DateTime.UtcNow;
    }
}

// ─── Domain/Exceptions/{{Name}}Exceptions.cs ────────────────────────────────
namespace {{Name}}.Domain.Exceptions;

public sealed class {{Name}}NotFoundException(Guid id)
    : Exception($"{{Name}} with id '{id}' was not found");

// ─── Application/Interfaces/I{{Name}}Repository.cs ──────────────────────────
namespace {{Name}}.Application.Interfaces;
using {{Name}}.Domain.Entities;

public interface I{{Name}}Repository
{
    Task<IEnumerable<{{Name}}Entity>> GetAllAsync(CancellationToken ct = default);
    Task<{{Name}}Entity?> GetByIdAsync(Guid id, CancellationToken ct = default);
    Task<{{Name}}Entity> AddAsync({{Name}}Entity entity, CancellationToken ct = default);
    Task UpdateAsync({{Name}}Entity entity, CancellationToken ct = default);
    Task DeleteAsync(Guid id, CancellationToken ct = default);
}

// ─── Application/DTOs/{{Name}}DTOs.cs ────────────────────────────────────────
namespace {{Name}}.Application.DTOs;

public record {{Name}}Response(Guid Id, string Name, DateTime CreatedAt, DateTime? UpdatedAt);
public record Create{{Name}}Request(string Name);
public record Update{{Name}}Request(string? Name);

// ─── Application/Services/{{Name}}Service.cs ─────────────────────────────────
namespace {{Name}}.Application.Services;

using {{Name}}.Application.DTOs;
using {{Name}}.Application.Interfaces;
using {{Name}}.Domain.Entities;
using {{Name}}.Domain.Exceptions;

public sealed class {{Name}}Service(I{{Name}}Repository repository)
{
    public async Task<IEnumerable<{{Name}}Response>> GetAllAsync(CancellationToken ct = default)
    {
        var items = await repository.GetAllAsync(ct);
        return items.Select(MapToResponse);
    }

    public async Task<{{Name}}Response> GetByIdAsync(Guid id, CancellationToken ct = default)
    {
        var entity = await repository.GetByIdAsync(id, ct)
            ?? throw new {{Name}}NotFoundException(id);
        return MapToResponse(entity);
    }

    public async Task<{{Name}}Response> CreateAsync(Create{{Name}}Request request, CancellationToken ct = default)
    {
        var entity = {{Name}}Entity.Create(request.Name);
        await repository.AddAsync(entity, ct);
        return MapToResponse(entity);
    }

    public async Task<{{Name}}Response> UpdateAsync(Guid id, Update{{Name}}Request request, CancellationToken ct = default)
    {
        var entity = await repository.GetByIdAsync(id, ct)
            ?? throw new {{Name}}NotFoundException(id);
        entity.Update(request.Name);
        await repository.UpdateAsync(entity, ct);
        return MapToResponse(entity);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct = default)
    {
        _ = await repository.GetByIdAsync(id, ct) ?? throw new {{Name}}NotFoundException(id);
        await repository.DeleteAsync(id, ct);
    }

    private static {{Name}}Response MapToResponse({{Name}}Entity e) =>
        new(e.Id, e.Name, e.CreatedAt, e.UpdatedAt);
}

// ─── Infrastructure/Repositories/{{Name}}Repository.cs ───────────────────────
namespace {{Name}}.Infrastructure.Repositories;

using {{Name}}.Application.Interfaces;
using {{Name}}.Domain.Entities;
using Microsoft.EntityFrameworkCore;

public sealed class {{Name}}Repository(AppDbContext context) : I{{Name}}Repository
{
    public async Task<IEnumerable<{{Name}}Entity>> GetAllAsync(CancellationToken ct = default) =>
        await context.{{Name_plural}}.OrderByDescending(x => x.CreatedAt).ToListAsync(ct);

    public async Task<{{Name}}Entity?> GetByIdAsync(Guid id, CancellationToken ct = default) =>
        await context.{{Name_plural}}.FirstOrDefaultAsync(x => x.Id == id, ct);

    public async Task<{{Name}}Entity> AddAsync({{Name}}Entity entity, CancellationToken ct = default)
    {
        context.{{Name_plural}}.Add(entity);
        await context.SaveChangesAsync(ct);
        return entity;
    }

    public async Task UpdateAsync({{Name}}Entity entity, CancellationToken ct = default)
    {
        context.{{Name_plural}}.Update(entity);
        await context.SaveChangesAsync(ct);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct = default)
    {
        await context.{{Name_plural}}.Where(x => x.Id == id).ExecuteDeleteAsync(ct);
    }
}

// ─── Api/Endpoints/{{Name}}Endpoints.cs (Minimal API) ────────────────────────
namespace {{Name}}.Api.Endpoints;

using {{Name}}.Application.DTOs;
using {{Name}}.Application.Services;
using {{Name}}.Domain.Exceptions;
using Microsoft.AspNetCore.Mvc;

public static class {{Name}}Endpoints
{
    public static IEndpointRouteBuilder Map{{Name}}Endpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/v1/{{name_plural}}")
            .WithTags("{{Name_plural}}")
            .WithOpenApi();

        group.MapGet("/", async ({{Name}}Service svc, CancellationToken ct) =>
            Results.Ok(await svc.GetAllAsync(ct)));

        group.MapGet("/{id:guid}", async (Guid id, {{Name}}Service svc, CancellationToken ct) =>
        {
            try { return Results.Ok(await svc.GetByIdAsync(id, ct)); }
            catch ({{Name}}NotFoundException ex) { return Results.NotFound(ex.Message); }
        });

        group.MapPost("/", async ([FromBody] Create{{Name}}Request req, {{Name}}Service svc, CancellationToken ct) =>
        {
            var created = await svc.CreateAsync(req, ct);
            return Results.Created($"/api/v1/{{name_plural}}/{created.Id}", created);
        });

        group.MapPut("/{id:guid}", async (Guid id, [FromBody] Update{{Name}}Request req, {{Name}}Service svc, CancellationToken ct) =>
        {
            try { return Results.Ok(await svc.UpdateAsync(id, req, ct)); }
            catch ({{Name}}NotFoundException ex) { return Results.NotFound(ex.Message); }
        });

        group.MapDelete("/{id:guid}", async (Guid id, {{Name}}Service svc, CancellationToken ct) =>
        {
            try { await svc.DeleteAsync(id, ct); return Results.NoContent(); }
            catch ({{Name}}NotFoundException ex) { return Results.NotFound(ex.Message); }
        });

        return app;
    }
}

// ─── Tests/{{Name}}ServiceTests.cs ────────────────────────────────────────────
namespace {{Name}}.Tests;

using NSubstitute;
using {{Name}}.Application.DTOs;
using {{Name}}.Application.Interfaces;
using {{Name}}.Application.Services;
using {{Name}}.Domain.Exceptions;
using Xunit;

public class {{Name}}ServiceTests
{
    private readonly I{{Name}}Repository _repo = Substitute.For<I{{Name}}Repository>();
    private readonly {{Name}}Service _sut;

    public {{Name}}ServiceTests() => _sut = new {{Name}}Service(_repo);

    [Fact]
    public async Task GetByIdAsync_ShouldThrow_WhenNotFound()
    {
        _repo.GetByIdAsync(Arg.Any<Guid>()).Returns(({{Name}}.Domain.Entities.{{Name}}Entity?)null);
        await Assert.ThrowsAsync<{{Name}}NotFoundException>(() => _sut.GetByIdAsync(Guid.NewGuid()));
    }

    [Fact]
    public async Task CreateAsync_ShouldReturnCreated()
    {
        var req = new Create{{Name}}Request("Test Name");
        _repo.AddAsync(Arg.Any<{{Name}}.Domain.Entities.{{Name}}Entity>())
             .Returns(x => x.ArgAt<{{Name}}.Domain.Entities.{{Name}}Entity>(0));
        var result = await _sut.CreateAsync(req);
        Assert.Equal("Test Name", result.Name);
    }
}
'''

DESCRIPTION = ".NET 8 Minimal API + Clean Architecture + EF Core + xUnit + NSubstitute"
TECH_STACK = [".NET 8", "C#", "Minimal API", "Entity Framework Core 8", "xUnit", "NSubstitute", "FluentValidation"]
