# Personal Virtual Book Library

A small Python command-line application created for a school project. The app lets a user create an account, sign in, and manage a personal virtual book library stored in a MySQL database.

## What It Does

This project allows users to:

- Create an account using an 8-digit student ID
- Sign in with a password
- Store passwords securely using `bcrypt`
- Add books to a personal library
- Save book details including title, author, genre, serial number, and book link
- View saved books in alphabetical order
- View detailed information for each saved book
- Remove books from the library
- Keep each user's book list separate by account

## How It Works

The program runs in the terminal and connects to a local MySQL database.

When the app starts, the user can either sign into an existing account or create a new one. Passwords are hashed before being stored in the database.

After signing in, the user can add books, view saved books, or remove books from their library. Book records are connected to the signed-in user's student ID, so each account has its own saved library.

## Requirements

- Python 3
- MySQL Server
- Python packages listed in `requirements.txt`

Install the Python requirements with:

```bash
pip install -r requirements.txt
```

## Database Setup

Create a MySQL database named:

```sql
CREATE DATABASE bookappdb;
```

Then create the required tables:

```sql
USE bookappdb;

CREATE TABLE logintbl (
    sid VARCHAR(8) PRIMARY KEY,
    spwd VARCHAR(255) NOT NULL
);

CREATE TABLE bookstbl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255),
    isbnfk VARCHAR(255),
    sid VARCHAR(8),
    cat VARCHAR(255),
    url TEXT,
    FOREIGN KEY (sid) REFERENCES logintbl(sid)
);
```

## Configuration

Update the database connection information in `bookapp.py` if needed:

```python
host="localhost"
user="root"
password="root"
database="bookappdb"
```

Use your own local MySQL username and password when running the project.

## Running the App

After setting up the database and installing the requirements, run:

```bash
python bookapp.py
```

## Project Purpose

This project was made for educational purposes to practice:

- Python programming
- MySQL database usage
- User authentication
- Password hashing
- Input validation
- Basic create, read, and delete database operations