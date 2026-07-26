terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Deployment environment (e.g. staging, prod)"
  type        = string
  default     = "prod"
}

# Immutable Evidence Store
resource "aws_s3_bucket" "evidence_store" {
  bucket = "helios-evidence-${var.environment}"
}

resource "aws_s3_bucket_versioning" "evidence_store_versioning" {
  bucket = aws_s3_bucket.evidence_store.id
  versioning_configuration {
    status = "Enabled"
  }
}

# PostGIS Database
resource "aws_db_instance" "helios_db" {
  identifier           = "helios-db-${var.environment}"
  engine               = "postgres"
  engine_version       = "16.3"
  instance_class       = "db.t4g.small"
  allocated_storage    = 50
  storage_type         = "gp3"
  db_name              = "helios"
  username             = "helios"
  manage_master_user_password = true
  skip_final_snapshot  = false
  backup_retention_period = 7
  publicly_accessible  = false

  vpc_security_group_ids = [aws_security_group.db_sg.id]
}

resource "aws_security_group" "db_sg" {
  name        = "helios-db-sg-${var.environment}"
  description = "Security group for Helios PostGIS database"

  ingress {
    description = "Allow Postgres from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"] # Mock VPC cidr
  }
}

# ECS Cluster for API and Workers
resource "aws_ecs_cluster" "helios_cluster" {
  name = "helios-cluster-${var.environment}"
}
