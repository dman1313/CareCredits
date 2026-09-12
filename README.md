# CareCredits

A centralized CPD (Continuing Professional Development) portal for Malaysian doctors to discover, register for, and track medical training. Featuring a searchable dashboard to filter courses by location, fee, difficulty, and CPD points, the app simplifies annual license renewal.

## Overview

CareCredits is built using a modern microservices architecture with three core components:

1. **Frontend (TypeScript)**: A responsive web application built with TypeScript and React, providing an intuitive interface for doctors to browse and manage CPD courses. User authentication is handled via Google OAuth for secure and seamless login.

2. **Backend (Python)**: A robust RESTful API built with Python (using FastAPI or Flask) that manages user data, course registrations, and CPD tracking. The backend connects to a PostgreSQL database for persistent storage and ensures data integrity and scalability.

3. **Scraper API Service (Python)**: A dedicated microservice that uses the Tavily API to gather up-to-date information about medical training courses, including details like course descriptions, dates, locations, and CPD points. This service ensures the portal always has fresh, accurate data.

## Features

- Google OAuth authentication for secure user login
- Searchable and filterable course dashboard (by location, fee, difficulty, CPD points)
- Real-time course data via Tavily-powered scraper
- User profile management and registration tracking
- CPD point tracking and renewal reminders

## Getting Started

1. Clone the repository.
2. Set up the environment for each service:
   - Frontend: Install Node.js and run `npm install && npm run dev`
   - Backend: Install Python 3.9+, create a virtual environment, and run `pip install -r requirements.txt`
   - Scraper API: Install dependencies and configure Tavily API key in `.env`
3. Start the services using Docker Compose or run them individually.
4. Access the frontend at `http://localhost:3000`.



