"""
Registry de templates por stack.
Cada template expõe MODULE_TEMPLATE, PROJECT_TEMPLATE, DESCRIPTION, TECH_STACK.
"""

from . import nestjs, spring_boot, python, dotnet

# Next.js e Angular — templates inline (estrutura mais simples)
_NEXTJS_TEMPLATE = '''
// ESTRUTURA NEXT.JS — App Router + Server Components
//
// src/
//  └── app/
//      ├── layout.tsx              ← Root layout
//      ├── page.tsx                ← Home page
//      └── {{name}}/
//          ├── page.tsx            ← List page (Server Component)
//          ├── [id]/page.tsx       ← Detail page
//          ├── _components/        ← Componentes locais (underscore = privado)
//          │   └── {{Name}}Card.tsx
//          ├── actions.ts          ← Server Actions (mutations)
//          └── types.ts            ← Tipos do módulo
//
// lib/
//  └── {{name}}/
//      ├── service.ts              ← Lógica de negócio
//      ├── repository.ts          ← Data access (Prisma/fetch)
//      └── validations.ts         ← Zod schemas

// lib/{{name}}/validations.ts
import { z } from 'zod';
export const create{{Name}}Schema = z.object({
  name: z.string().min(1).max(255),
  // ← adicionar campos
});
export type Create{{Name}}Input = z.infer<typeof create{{Name}}Schema>;

// lib/{{name}}/repository.ts — Repository Pattern
export interface I{{Name}}Repository {
  findAll(): Promise<{{Name}}[]>;
  findById(id: string): Promise<{{Name}} | null>;
  create(data: Create{{Name}}Input): Promise<{{Name}}>;
  update(id: string, data: Partial<Create{{Name}}Input>): Promise<{{Name}}>;
  delete(id: string): Promise<void>;
}

// app/{{name}}/actions.ts — Server Actions
'use server';
import { revalidatePath } from 'next/cache';
import { {{Name}}Service } from '@/lib/{{name}}/service';

export async function create{{Name}}Action(data: FormData) {
  const service = new {{Name}}Service();
  await service.create(Object.fromEntries(data) as any);
  revalidatePath('/{{name}}');
}
'''

_ANGULAR_TEMPLATE = '''
// ESTRUTURA ANGULAR — Standalone Components + Signals
//
// src/app/
//  └── features/
//      └── {{name}}/
//          ├── {{name}}.routes.ts          ← Lazy routes
//          ├── components/
//          │   ├── {{name}}-list/
//          │   │   ├── {{name}}-list.component.ts
//          │   │   └── {{name}}-list.component.html
//          │   └── {{name}}-form/
//          │       └── {{name}}-form.component.ts
//          ├── services/
//          │   └── {{name}}.service.ts     ← HTTP + state (Signals)
//          ├── models/
//          │   └── {{name}}.model.ts       ← Interfaces do domínio
//          └── store/
//              └── {{name}}.store.ts       ← SignalStore (NgRx Signals)

// services/{{name}}.service.ts — com Signals
import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class {{Name}}Service {
  private http = inject(HttpClient);
  private _items = signal<{{Name}}[]>([]);
  private _loading = signal(false);

  readonly items = this._items.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly count = computed(() => this._items().length);

  async loadAll(): Promise<void> {
    this._loading.set(true);
    try {
      const data = await firstValueFrom(this.http.get<{{Name}}[]>('/api/{{name_plural}}'));
      this._items.set(data);
    } finally {
      this._loading.set(false);
    }
  }
}

// ← models, components e routes seguem o mesmo padrão standalone
'''

REGISTRY: dict[str, dict] = {
    "nestjs": {
        "module_template": nestjs.MODULE_TEMPLATE,
        "project_template": nestjs.PROJECT_TEMPLATE,
        "description": nestjs.DESCRIPTION,
        "tech_stack": nestjs.TECH_STACK,
    },
    "nextjs": {
        "module_template": _NEXTJS_TEMPLATE,
        "project_template": _NEXTJS_TEMPLATE,
        "description": "Next.js 14+ App Router + TypeScript + Tailwind + Server Actions + Prisma",
        "tech_stack": ["Next.js 14", "TypeScript", "Tailwind CSS", "Prisma", "Zod", "React", "Jest"],
    },
    "angular": {
        "module_template": _ANGULAR_TEMPLATE,
        "project_template": _ANGULAR_TEMPLATE,
        "description": "Angular 17+ Standalone Components + Signals + NgRx Signal Store",
        "tech_stack": ["Angular 17", "TypeScript", "NgRx Signals", "RxJS", "Jasmine", "Karma"],
    },
    "spring-boot": {
        "module_template": spring_boot.MODULE_TEMPLATE,
        "project_template": spring_boot.MODULE_TEMPLATE,
        "description": spring_boot.DESCRIPTION,
        "tech_stack": spring_boot.TECH_STACK,
    },
    "python": {
        "module_template": python.MODULE_TEMPLATE,
        "project_template": python.MODULE_TEMPLATE,
        "description": python.DESCRIPTION,
        "tech_stack": python.TECH_STACK,
    },
    "dotnet": {
        "module_template": dotnet.MODULE_TEMPLATE,
        "project_template": dotnet.MODULE_TEMPLATE,
        "description": dotnet.DESCRIPTION,
        "tech_stack": dotnet.TECH_STACK,
    },
}


def get_template(stack: str) -> dict:
    """Retorna o template da stack. Normaliza o nome."""
    key = stack.lower().replace("_", "-")
    if key not in REGISTRY:
        available = ", ".join(REGISTRY.keys())
        raise ValueError(f"Stack '{stack}' não suportada. Disponíveis: {available}")
    return REGISTRY[key]
