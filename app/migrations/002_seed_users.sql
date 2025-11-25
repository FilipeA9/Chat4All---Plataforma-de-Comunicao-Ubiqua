-- Chat4All API Hub - Seed Data Migration
-- Creates 5 test users for development and testing
-- Run this after 001_initial_schema.sql

-- Insert test users (password for all: "password123")
-- Password hash generated using bcrypt with 12 rounds

INSERT INTO users (username, email, password_hash, full_name) VALUES
('user1', 'user1@chat4all.com', '$2b$12$CvO.4HskWdc3IyRWeQrK3.nS2RngRILlEBnTMP6.ppH.E7bLdRvhm', 'User One'),
('user2', 'user2@chat4all.com', '$2b$12$CvO.4HskWdc3IyRWeQrK3.nS2RngRILlEBnTMP6.ppH.E7bLdRvhm', 'User Two'),
('user3', 'user3@chat4all.com', '$2b$12$CvO.4HskWdc3IyRWeQrK3.nS2RngRILlEBnTMP6.ppH.E7bLdRvhm', 'User Three'),
('user4', 'user4@chat4all.com', '$2b$12$CvO.4HskWdc3IyRWeQrK3.nS2RngRILlEBnTMP6.ppH.E7bLdRvhm', 'User Four'),
('user5', 'user5@chat4all.com', '$2b$12$CvO.4HskWdc3IyRWeQrK3.nS2RngRILlEBnTMP6.ppH.E7bLdRvhm', 'User Five');

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
