-- Chat4All API Hub - Seed Data Migration
-- Creates 5 test users for development and testing
-- Run this after 001_initial_schema.sql

-- Insert test users (password for all: "password123")
-- Password hash generated using bcrypt with 12 rounds

-- INSERT INTO users (username, email, password_hash, full_name) VALUES
-- ('user1', 'user1@chat4all.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU8h/EM7RJzu', 'User One'),
-- ('user2', 'user2@chat4all.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU8h/EM7RJzu', 'User Two'),
-- ('user3', 'user3@chat4all.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU8h/EM7RJzu', 'User Three'),
-- ('user4', 'user4@chat4all.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU8h/EM7RJzu', 'User Four'),
-- ('user5', 'user5@chat4all.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU8h/EM7RJzu', 'User Five');

-- Seed users for testing (plain text passwords)
-- AVISO: Usar senhas em texto plano apenas em ambiente acadêmico/desenvolvimento

INSERT INTO users (username, password) VALUES
('user1', 'password123'),
('user2', 'password123'),
('user3', 'password123'),
('admin', 'admin123');

-- Verify insertion
SELECT id, username, email, full_name, created_at FROM users;

-- Test user credentials:
-- username: user1, password: password123
-- username: user2, password: password123
-- username: user3, password: password123
-- username: user4, password: password123
-- username: user5, password: password123

-- Note: In production, users should be created via API with unique passwords
-- These test users are for development and testing purposes only
