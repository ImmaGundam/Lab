import os
import bcrypt  # type: ignore
import mysql.connector  # type: ignore
from mysql.connector import Error  # type: ignore
import re

# Function to create a database connection
def create_connection():
    connection = None
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",  
            password="root", 
            database="bookappdb"
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"The error '{e}' occurred")
    return connection

# Function to execute a query
def execute_query(query, data=None):
    connection = create_connection()
    if connection:
        cursor = connection.cursor()
        try:
            if data:
                cursor.execute(query, data)
            else:
                cursor.execute(query)
            connection.commit()
            return cursor.lastrowid
        except Error as e:
            print(f"The error '{e}' occurred")
        finally:
            cursor.close()
            connection.close()

# Function to fetch data from the database
def fetch_query(query, data=None):
    connection = create_connection()
    if connection:
        cursor = connection.cursor()
        try:
            if data:
                cursor.execute(query, data)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            return result
        except Error as e:
            print(f"The error '{e}' occurred")
        finally:
            cursor.close()
            connection.close()

# Function to check if the username exists
def username_exists(username):
    query = "SELECT * FROM logintbl WHERE sid = %s"
    result = fetch_query(query, (username,))
    return len(result) > 0

# Function to validate username
def validate_username(username):
    return re.fullmatch(r'\d{8}', username) is not None

# Function to validate password
def validate_password(password):
    return len(password) >= 6 and re.search(r'[A-Za-z]', password) and re.search(r'[0-9]', password)

# Function to hash a password
def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed

# Function to check a hashed password
def check_password(stored_password, provided_password):
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password)

# Function to create a new account
def create_account():
    while True:
        clear_console()
        username = input("Enter your 8 digit student ID to create your account: ")
        if not validate_username(username):
            print("Invalid username.")
            continue
        if username_exists(username):
            clear_console()
            print(f"The username '{username}' already exists. Please choose another.")
        else:
            password = input("Enter a password (at least 6 characters, must include both letters and numbers): ")
            if not validate_password(password):
                print("Invalid password. It must be at least 6 characters long and include both letters and numbers.")
                continue
            hashed_password = hash_password(password).decode('utf-8')
            query = "INSERT INTO logintbl (sid, spwd) VALUES (%s, %s)"
            execute_query(query, (username, hashed_password))
            clear_console()
            print(f"Account created successfully. Your username is '{username}'.")
            return username

# Function to sign in
def sign_in():
    while True:
        clear_console()
        username = input("Enter your 8 digit student ID to sign in: ")
        if not validate_username(username):
            print("Invalid username. It must be exactly 8 digits.")
            continue
        if username_exists(username):
            password = input("Enter your password: ")
            query = "SELECT spwd FROM logintbl WHERE sid = %s"
            result = fetch_query(query, (username,))
            stored_password = result[0][0] if result else None
            if stored_password and check_password(stored_password.encode('utf-8'), password):
                clear_console()
                print(f"Signed in successfully. Welcome back, {username}!")
                return username  # Ensure username is returned after successful login
            else:
                print("Incorrect password, try again.")  # Add debug statement for incorrect password
                continue
        else:
            clear_console()
            print("That username doesn't exist. Would you like to \n 1. Try a different username \n 2. Create an account")
            choice = input("Enter 1 or 2: ")
            if choice == '1':
                continue
            elif choice == '2':
                return create_account()  # Ensure return here too
            else:
                clear_console()
                print("Invalid choice, returning to sign in.")
                continue

# Function to add a book to the library
def add_book(username):
    while True:
        clear_console()
        title = input("Enter the book name: ")

        # Check for duplicate book names
        query = "SELECT * FROM bookstbl WHERE title = %s AND sid = %s"
        existing_books = fetch_query(query, (title, username))

        if existing_books:
            print(f"The book '{title}' already exists.")
            choice = input("Press 1 to continue and replace the existing one \n 2 to return and add a new book \n 3 to view current books: ")
            if choice == '1':
                query = "DELETE FROM bookstbl WHERE title = %s AND sid = %s"
                execute_query(query, (title, username))
            elif choice == '2':
                continue
            elif choice == '3':
                view_books(username)
                continue
            else:
                clear_console()
                print("Invalid choice, returning to book selection.")
                continue

        author = input("Enter the author: ")
        genre = input("Enter the genre: ")
        serial_number = input("Enter the serial number: ")
        link = input("Enter the link to the book: ")
        query = """
            INSERT INTO bookstbl (title, author, isbnfk, sid, cat, url)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        execute_query(query, (title, author, serial_number, username, genre, link))
        clear_console()
        print("Book added successfully.")
        
        choice = input("To return to book selection enter 1, to add another book enter 2: ")
        if choice == '1':
            break
        elif choice == '2':
            clear_console()
            continue
        else:
            clear_console()
            print("Invalid choice, returning to book selection.")
            break

# Function to view existing books in alphabetical order
def view_books(username):
    clear_console()
    query = "SELECT title, author, cat, isbnfk, url FROM bookstbl WHERE sid = %s ORDER BY title"
    books = fetch_query(query, (username,))
    if not books:
        print("No books found in the library.")
        return

    print("Books in your library:")
    for index, book in enumerate(books):
        print(f"{index + 1}. {book[0]}")

    while True:
        try:
            choice = int(input("\nEnter the number of the book you want to see more information about, or enter 0 to remove a book: "))
            if choice == 0:
                remove_book(username)
                return  # Return to the main menu after removing a book
            elif 1 <= choice <= len(books):
                selected_book = books[choice - 1]
                clear_console()
                print("\nBook Details:\n")
                print(f"Title: {selected_book[0]}")
                print(f"Author: {selected_book[1]}")
                print(f"Genre: {selected_book[2]}")
                print(f"Serial Number: {selected_book[3]}")
                print(f"Link: {selected_book[4]}")
                break
            else:
                clear_console()
                print(f"Invalid choice, please select a number between 1 and {len(books)}.")
        except ValueError:
            clear_console()
            print("Invalid input, please enter a number.")

def remove_book(username):
    while True:
        try:
            choice = int(input("\nEnter the number of the book you want to remove, or enter 0 to cancel: "))
            if choice == 0:
                clear_console()
                print("Removal canceled.")
                break
            else:
                query = "SELECT title FROM bookstbl WHERE sid = %s ORDER BY title"
                books = fetch_query(query, (username,))
                book_titles = [book[0] for book in books]
                if 1 <= choice <= len(book_titles):
                    selected_title = book_titles[choice - 1]
                    query = "DELETE FROM bookstbl WHERE title = %s AND sid = %s"
                    execute_query(query, (selected_title, username))
                    clear_console()
                    print(f"The book '{selected_title}' has been removed.")
                    break
                else:
                    clear_console()
                    print(f"Invalid choice, please select a number between 0 and {len(book_titles)}.")
        except ValueError:
            clear_console()
            print("Invalid input, please enter a number.")

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    clear_console()
    print("Hi, welcome to your personal virtual book library where you can store links and information for all of your books.")
    
    while True:
        choice = input("Do you want to \n1. Sign into an existing account \n2. Create an account \n(enter 1 or 2): ")
        if choice == '1':
            username = sign_in()
            if username:  # Check if username is not None (successful login)
                break
        elif choice == '2':
            username = create_account()
            if username:  # Check if username is not None (successful account creation)
                break
        else:
            clear_console()
            print("Invalid choice, please enter 1 or 2.")
    
    while True:
        choice = input("Do you want to \n1. Add a book \n2. View your already existing books, \n3. Log Out \n(enter 1, 2, or 3): ")
        if choice == '1':
            add_book(username)
        elif choice == '2':
            view_books(username)
        elif choice == '3':
            break
        else:
            clear_console()
            print("Invalid choice, please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()