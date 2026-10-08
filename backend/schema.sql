-- =====================================================================
-- SISTEMA POS PWA - DDL SCHEMA (MySQL 8.0+)
-- Arquitectura Multi-Tenant SaaS con Soporte Offline-First e Idempotencia
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `sistema_pos_pwa` 
  DEFAULT CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;

USE `sistema_pos_pwa`;

SET FOREIGN_KEY_CHECKS = 0;

-- 1. TENANTS (Empresas / Tiendas aisladas)
CREATE TABLE IF NOT EXISTS `tenants` (
    `id` VARCHAR(36) NOT NULL,
    `business_name` VARCHAR(150) NOT NULL,
    `tax_id` VARCHAR(50) DEFAULT NULL COMMENT 'NIT / RUC / CIF / RFC',
    `phone` VARCHAR(30) DEFAULT NULL,
    `email` VARCHAR(120) DEFAULT NULL,
    `address` VARCHAR(255) DEFAULT NULL,
    `currency_symbol` VARCHAR(5) NOT NULL DEFAULT '$',
    `status` ENUM('ACTIVE', 'SUSPENDED', 'TRIAL') NOT NULL DEFAULT 'ACTIVE',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. USERS (Usuarios del sistema asociados estrictamente a un tenant)
CREATE TABLE IF NOT EXISTS `users` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `full_name` VARCHAR(120) NOT NULL,
    `email` VARCHAR(120) NOT NULL,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` ENUM('ADMIN', 'MANAGER', 'CASHIER') NOT NULL DEFAULT 'CASHIER',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_tenant_user_email` (`tenant_id`, `email`),
    INDEX `idx_users_tenant` (`tenant_id`),
    CONSTRAINT `fk_users_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. CATEGORIES (Categorías de productos por tenant)
CREATE TABLE IF NOT EXISTS `categories` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `description` VARCHAR(255) DEFAULT NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_categories_tenant` (`tenant_id`),
    CONSTRAINT `fk_categories_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. PRODUCTS (Catálogo de productos con inventario y precios)
CREATE TABLE IF NOT EXISTS `products` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `category_id` VARCHAR(36) DEFAULT NULL,
    `barcode` VARCHAR(64) DEFAULT NULL,
    `name` VARCHAR(150) NOT NULL,
    `cost_price` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `sale_price` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `stock` INT NOT NULL DEFAULT 0,
    `min_stock` INT NOT NULL DEFAULT 5,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_products_tenant_active` (`tenant_id`, `is_active`),
    INDEX `idx_products_barcode` (`tenant_id`, `barcode`),
    INDEX `idx_products_category` (`tenant_id`, `category_id`),
    CONSTRAINT `fk_products_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_products_category` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. SALES (Encabezado de transacciones de venta)
-- client_sync_id garantiza idempotencia: ventas registradas offline no se duplican en reintentos
CREATE TABLE IF NOT EXISTS `sales` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL,
    `client_sync_id` VARCHAR(64) NOT NULL COMMENT 'UUID único generado en terminal local offline',
    `invoice_number` VARCHAR(30) NOT NULL,
    `subtotal` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `tax` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `discount` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `total` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `payment_method` ENUM('CASH', 'CARD', 'TRANSFER', 'OTHER') NOT NULL DEFAULT 'CASH',
    `amount_paid` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `change_due` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `sync_status` ENUM('ONLINE', 'SYNCED_OFFLINE') NOT NULL DEFAULT 'ONLINE',
    `notes` VARCHAR(255) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_tenant_client_sync` (`tenant_id`, `client_sync_id`),
    INDEX `idx_sales_tenant_created` (`tenant_id`, `created_at`),
    INDEX `idx_sales_user` (`tenant_id`, `user_id`),
    CONSTRAINT `fk_sales_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sales_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. SALE_ITEMS (Detalle de productos por cada venta)
-- Guarda unit_cost al momento de la venta para calcular ganancias netas históricas fidedignas
CREATE TABLE IF NOT EXISTS `sale_items` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `sale_id` VARCHAR(36) NOT NULL,
    `product_id` VARCHAR(36) NOT NULL,
    `product_name` VARCHAR(150) NOT NULL,
    `quantity` INT NOT NULL DEFAULT 1,
    `unit_cost` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `unit_price` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `subtotal` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `total` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (`id`),
    INDEX `idx_sale_items_sale` (`tenant_id`, `sale_id`),
    INDEX `idx_sale_items_product` (`tenant_id`, `product_id`),
    CONSTRAINT `fk_sale_items_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sale_items_sale` FOREIGN KEY (`sale_id`) REFERENCES `sales` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sale_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. SYNC_AUDIT_LOG (Bitácora de sincronización offline <-> nube)
CREATE TABLE IF NOT EXISTS `sync_audit_log` (
    `id` VARCHAR(36) NOT NULL,
    `tenant_id` VARCHAR(36) NOT NULL,
    `client_sync_id` VARCHAR(64) NOT NULL,
    `device_id` VARCHAR(100) DEFAULT NULL,
    `status` ENUM('SUCCESS', 'ALREADY_SYNCED', 'CONFLICT', 'ERROR') NOT NULL,
    `details` TEXT DEFAULT NULL,
    `synced_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_sync_log_tenant` (`tenant_id`, `synced_at`),
    CONSTRAINT `fk_sync_log_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
