"""
Template Spring Boot — Clean Architecture com Java.
Padrões: Repository, Service Interface, DTO, MapStruct, JUnit 5.
"""

MODULE_TEMPLATE = '''
// ═══════════════════════════════════════════════════════════════════════════════
// ESTRUTURA DE MÓDULO SPRING BOOT — CLEAN ARCHITECTURE
// ═══════════════════════════════════════════════════════════════════════════════
//
// src/main/java/com/{{package}}/{{name}}/
//  ├── controller/
//  │   └── {{Name}}Controller.java
//  ├── service/
//  │   ├── {{Name}}Service.java         ← interface (DIP)
//  │   └── impl/
//  │       └── {{Name}}ServiceImpl.java
//  ├── repository/
//  │   └── {{Name}}Repository.java      ← JpaRepository
//  ├── entity/
//  │   └── {{Name}}Entity.java
//  ├── dto/
//  │   ├── {{Name}}RequestDTO.java
//  │   └── {{Name}}ResponseDTO.java
//  ├── mapper/
//  │   └── {{Name}}Mapper.java          ← MapStruct
//  └── exception/
//      └── {{Name}}NotFoundException.java

// ─── ENTITY ────────────────────────────────────────────────────────────────
// src/main/java/com/{{package}}/{{name}}/entity/{{Name}}Entity.java

package com.{{package}}.{{name_lower}}.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "{{name_plural}}")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class {{Name}}Entity {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    // ← adicionar @Column para cada campo do domínio

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}

// ─── REQUEST DTO ────────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.dto;

import jakarta.validation.constraints.*;
import lombok.*;

@Data @Builder @NoArgsConstructor @AllArgsConstructor
public class {{Name}}RequestDTO {
    // ← adicionar @NotNull, @NotBlank, @Size etc.
    @NotBlank(message = "Name is required")
    private String name;
}

// ─── RESPONSE DTO ───────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.dto;

import lombok.*;
import java.time.LocalDateTime;
import java.util.UUID;

@Data @Builder @NoArgsConstructor @AllArgsConstructor
public class {{Name}}ResponseDTO {
    private UUID id;
    // ← campos do domínio
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}

// ─── SERVICE INTERFACE (DIP) ────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.service;

import com.{{package}}.{{name_lower}}.dto.*;
import java.util.List;
import java.util.UUID;

public interface {{Name}}Service {
    List<{{Name}}ResponseDTO> findAll();
    {{Name}}ResponseDTO findById(UUID id);
    {{Name}}ResponseDTO create({{Name}}RequestDTO dto);
    {{Name}}ResponseDTO update(UUID id, {{Name}}RequestDTO dto);
    void delete(UUID id);
}

// ─── SERVICE IMPL ───────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.service.impl;

import com.{{package}}.{{name_lower}}.dto.*;
import com.{{package}}.{{name_lower}}.entity.{{Name}}Entity;
import com.{{package}}.{{name_lower}}.exception.{{Name}}NotFoundException;
import com.{{package}}.{{name_lower}}.mapper.{{Name}}Mapper;
import com.{{package}}.{{name_lower}}.repository.{{Name}}Repository;
import com.{{package}}.{{name_lower}}.service.{{Name}}Service;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class {{Name}}ServiceImpl implements {{Name}}Service {
    private final {{Name}}Repository repository;
    private final {{Name}}Mapper mapper;

    @Override
    public List<{{Name}}ResponseDTO> findAll() {
        return repository.findAll().stream()
            .map(mapper::toResponse)
            .toList();
    }

    @Override
    public {{Name}}ResponseDTO findById(UUID id) {
        return repository.findById(id)
            .map(mapper::toResponse)
            .orElseThrow(() -> new {{Name}}NotFoundException(id));
    }

    @Override
    @Transactional
    public {{Name}}ResponseDTO create({{Name}}RequestDTO dto) {
        {{Name}}Entity entity = mapper.toEntity(dto);
        return mapper.toResponse(repository.save(entity));
    }

    @Override
    @Transactional
    public {{Name}}ResponseDTO update(UUID id, {{Name}}RequestDTO dto) {
        {{Name}}Entity entity = repository.findById(id)
            .orElseThrow(() -> new {{Name}}NotFoundException(id));
        mapper.updateEntity(dto, entity);
        return mapper.toResponse(repository.save(entity));
    }

    @Override
    @Transactional
    public void delete(UUID id) {
        if (!repository.existsById(id)) throw new {{Name}}NotFoundException(id);
        repository.deleteById(id);
    }
}

// ─── REPOSITORY ─────────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.repository;
import org.springframework.data.jpa.repository.JpaRepository;
import com.{{package}}.{{name_lower}}.entity.{{Name}}Entity;
import java.util.UUID;
public interface {{Name}}Repository extends JpaRepository<{{Name}}Entity, UUID> {}

// ─── CONTROLLER ─────────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.controller;

import com.{{package}}.{{name_lower}}.dto.*;
import com.{{package}}.{{name_lower}}.service.{{Name}}Service;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/{{name_plural}}")
@RequiredArgsConstructor
public class {{Name}}Controller {
    private final {{Name}}Service service;

    @GetMapping
    public ResponseEntity<List<{{Name}}ResponseDTO>> findAll() {
        return ResponseEntity.ok(service.findAll());
    }

    @GetMapping("/{id}")
    public ResponseEntity<{{Name}}ResponseDTO> findById(@PathVariable UUID id) {
        return ResponseEntity.ok(service.findById(id));
    }

    @PostMapping
    public ResponseEntity<{{Name}}ResponseDTO> create(@Valid @RequestBody {{Name}}RequestDTO dto) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(dto));
    }

    @PutMapping("/{id}")
    public ResponseEntity<{{Name}}ResponseDTO> update(@PathVariable UUID id, @Valid @RequestBody {{Name}}RequestDTO dto) {
        return ResponseEntity.ok(service.update(id, dto));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable UUID id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}

// ─── EXCEPTION ───────────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.exception;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;
import java.util.UUID;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class {{Name}}NotFoundException extends RuntimeException {
    public {{Name}}NotFoundException(UUID id) {
        super("{{Name}} not found with id: " + id);
    }
}

// ─── TEST ────────────────────────────────────────────────────────────────────
package com.{{package}}.{{name_lower}}.service;

import com.{{package}}.{{name_lower}}.exception.{{Name}}NotFoundException;
import com.{{package}}.{{name_lower}}.repository.{{Name}}Repository;
import com.{{package}}.{{name_lower}}.mapper.{{Name}}Mapper;
import com.{{package}}.{{name_lower}}.service.impl.{{Name}}ServiceImpl;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class {{Name}}ServiceTest {
    @Mock private {{Name}}Repository repository;
    @Mock private {{Name}}Mapper mapper;
    @InjectMocks private {{Name}}ServiceImpl service;

    @Test
    void shouldThrowNotFoundWhenIdDoesNotExist() {
        UUID id = UUID.randomUUID();
        when(repository.findById(id)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.findById(id))
            .isInstanceOf({{Name}}NotFoundException.class);
    }
}
'''

DESCRIPTION = "Spring Boot 3 com Clean Architecture, JPA, MapStruct, Lombok, JUnit 5 e Mockito"
TECH_STACK = ["Spring Boot 3", "Java 21", "Spring Data JPA", "Hibernate", "MapStruct", "Lombok", "JUnit 5", "Mockito"]
