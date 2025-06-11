#!/bin/bash
docker-compose -f docker-compose-echo-core.yml down --volumes --remove-orphans
docker-compose -f docker-compose-echo-spec.yml down --volumes --remove-orphans
docker-compose -f docker-compose-student.yml down --volumes --remove-orphans
docker-compose -f docker-compose-teacher.yml down --volumes --remove-orphans


docker-compose -f docker-compose-echo-core.yml up --build -d
docker-compose -f docker-compose-echo-spec.yml up --build -d
docker-compose -f docker-compose-student.yml up --build -d
docker-compose -f docker-compose-teacher.yml up --build -d

