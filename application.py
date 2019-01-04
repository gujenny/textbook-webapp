import os
import requests
import geopy.distance

from validate_email import validate_email

# path for the folder that the cover images the user uploads are saved in
UPLOAD_FOLDER = './static/cover'

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


db = SQL("sqlite:///textbook.db")

# source: https://stackoverflow.com/questions/15775893/college-university-data-api
# source: https://nces.ed.gov/ipeds/use-the-data
# gets dictionary of postsecondary schools in U.S.
SCHOOLS = {}
with open("schools.csv", "r") as file:
    # skips first line in file
    # source: https://stackoverflow.com/questions/4796764/read-file-from-line-2-or-skip-header-row
    next(file)
    for line in file.readlines():
        # splits line into elements separted by a comma
        # source: https://stackoverflow.com/questions/15286560/python-using-excel-csv-file-to-read-only-certain-columns-and-rows/15287487
        element = line.split(",")
        # source: https://stackoverflow.com/questions/40950791/remove-quotes-from-string-in-python/40950987
        # key is the school name, value is [latitude, longitude]
        SCHOOLS[element[-3].strip('\"')] = [float(element[-2].strip('\"')), float(element[-1].rstrip().strip('\"'))]


@app.route("/")
@login_required
def index():
    """Shows the user's books"""
    # the books the user has for sale
    sell = db.execute("SELECT title, author, price, usd, id FROM books WHERE seller_id=:user AND sold=0", user=session["user_id"])
    # books the user has bought
    bought = db.execute("SELECT title, author, price, usd, id FROM books WHERE buyer_id=:user", user=session["user_id"])
    # books the user has successfully sold
    sold = db.execute("SELECT title, author, price, usd, id FROM books WHERE seller_id=:user AND sold=1", user=session["user_id"])
    return render_template("index.html", sell=sell, bought=bought, sold=sold)


@app.route("/contactBuyer", methods=["GET", "POST"])
@login_required
def contactBuyer():
    """Shows the contact information of the buyer so the user can contact them"""
    if request.method == "GET":
        return redirect("/")
    else:
        # selects the buyer
        contact = db.execute("SELECT college, email FROM users WHERE id=:user", user=db.execute(
            "SELECT buyer_id FROM books WHERE id=:bookid", bookid=request.form.get("bookId"))[0]["buyer_id"])[0]
        return render_template("contact.html", contact=contact)


@app.route("/contactSeller", methods=["GET", "POST"])
@login_required
def contactSeller():
    """Shows the contact information of the seller so the user can contact them"""
    if request.method == "GET":
        return redirect("/")
    else:
        # selects the seller
        contact = db.execute("SELECT college, email FROM users WHERE id=:user", user=db.execute(
            "SELECT seller_id FROM books WHERE id=:bookid", bookid=request.form.get("bookId"))[0]["seller_id"])[0]
        return render_template("contact.html", contact=contact)


@app.route("/browse", methods=["GET", "POST"])
@login_required
def browse():
    """Allows the user to search for a book and filter results based on location"""
    if request.method == "GET":
        return render_template("browse.html")
    else:
        # makes sure user submitted all required search fields
        for field in ["searchInput", "distance"]:
            if not request.form.get(field):
                return apology("Missing" + field, 400)
        search = request.form.get("searchInput")
        dist = request.form.get("distance")
        # source: https://www.w3schools.com/sql/sql_and_or.asp
        # source: https://www.techonthenet.com/sql/and_or.php
        # source using patterns in SQL: https://www.essentialsql.com/get-ready-to-learn-sql-server-filter-results-using-patterns/
        # choose all books that match the user's search input (does not have to be precise match)
        books = db.execute(
            "SELECT title, author, price, usd, quality, seller_id, id, cover from books WHERE sold=0 AND (title LIKE :pattern OR author LIKE :pattern OR isbn LIKE :pattern)", pattern="%" + search + "%")
        # selects the user's school
        mySchool = SCHOOLS[db.execute("SELECT college FROM users WHERE id=:userid", userid=session["user_id"])[0]["college"]]
        listBooks = []
        for book in books:
            # selects the school that the book's seller belongs to
            seller = db.execute("SELECT college FROM users WHERE id=:sellerid", sellerid=book["seller_id"])[0]["college"]
            # source: https://stackoverflow.com/questions/19412462/getting-distance-between-two-points-based-on-latitude-longitude
            # source: https://pypi.org/project/geopy/
            # calculates the distance between the seller's and potential buyer's schools to see if it is within the range the user specified
            if geopy.distance.distance((mySchool[0], mySchool[1]), (SCHOOLS[seller][0], SCHOOLS[seller][1])).miles < float(dist):
                book["school"] = seller
                listBooks.append(book)
        # if no books match the search, return a page that gives no results and tells the user to search again
        if len(listBooks) == 0:
            return render_template("blank.html")
        return render_template("results.html", books=listBooks)


@app.route("/buy", methods=["POST", "GET"])
@login_required
def buy():
    """User buys book"""
    if request.method == "GET":
        return redirect("/")
    else:
        # id of book the user is trying to buy
        book_id = request.form.get("bookId")
        # source: https://www.dofactory.com/sql/update
        # updates database so that the book is "sold" and updates the buyer_id
        db.execute("UPDATE books SET sold=1, buyer_id=:userid WHERE id=:bookid", bookid=book_id, userid=session["user_id"])
        return render_template("bought.html", book=db.execute("SELECT title, usd from books WHERE id=:bookid", bookid=book_id)[0])


@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    """Allows user to change their password"""
    if request.method == "GET":
        return render_template("change.html")
    else:
        # makes sure user has submitted everything in the required fields
        for field in ["old password", "new password", "confirmation"]:
            if not request.form.get(field):
                return apology("Missing " + field, 400)
        # selects the user who is currently logged in
        user = db.execute("SELECT password_hash from users WHERE id=:id", id=session["user_id"])
        # makes sure user correctly submits current password
        if not check_password_hash(user[0]["password_hash"], request.form.get("old password")):
            return apology("Password incorrect", 400)
        # makes sure new password and confirmation match
        if request.form.get("new password") != request.form.get("confirmation"):
            return apology("New password and confirmation don't match", 400)
        # makes sure new password is different from old password
        if request.form.get("new password") == request.form.get("old password"):
            return apology("Cannot use same password as before", 400)
        # updates password hash in the users table
        db.execute("UPDATE users SET password_hash=:hash WHERE id=:id", hash=generate_password_hash(
            request.form.get("new password")), id=session["user_id"])
        return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    user = request.args.get("user")
    # looks through all the users in the table
    if not len(user) or db.execute("SELECT 1 FROM users WHERE user=:user", user=user.lower()):
        return jsonify(False)
    else:
        return jsonify(True)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html", schools=SCHOOLS)
    else:
        # makes sure user has submitted all the required fields
        for field in ["user", "college", "email", "password", "confirmation"]:
            if not request.form.get(field):
                return apology(f"{field} is missing!", 400)
        # makes sure user's password and confirmation match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match!", 400)
        # sources for validating an email address: https://pypi.org/project/validate_email/, https://stackoverflow.com/questions/8022530/python-check-for-valid-email-address
        if not validate_email(request.form.get("email")):
            return apology("Email is not valid", 400)
        # source for using generate_password_hash: http://werkzeug.pocoo.org/docs/0.14/utils/#werkzeug.security.generate_password_hash
        # inserts new user into the users table
        result = db.execute("INSERT INTO users (user, college, email, password_hash) VALUES(:user, :college, :email, :hash)", user=request.form.get(
            "user").lower(), college=request.form.get("college"), email=request.form.get("email"), hash=generate_password_hash(request.form.get("password")))
        # if the db.execute fails, the username has already been taken
        if not result:
            return apology("Username is already taken!", 400)
        session.clear()
        # logs the new user in
        session["user_id"] = result
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Lets user put a book up for sale"""
    if request.method == "GET":
        # returns the form for a user to sell a book
        return render_template("sell.html")
    else:
        # makes sure user has filled out all required fields
        for field in ["isbn", "price", "quality"]:
            if not request.form.get(field):
                return apology("Missing " + field, 400)
        isbn = request.form.get("isbn")
        # source: https://stackoverflow.com/questions/41469/how-to-fetch-a-book-title-from-an-isbn-number
        # source: https://developers.google.com/books/docs/v1/reference/
        # source: https://stackoverflow.com/questions/645312/what-is-the-quickest-way-to-http-get-in-python
        # source: https://www.youtube.com/watch?v=19-LOqdI61k
        # uses the Google Books API to use the isbn to search for a book's title, author, etc.
        bookInfo = requests.get("https://www.googleapis.com/books/v1/volumes?q=isbn:" + isbn).json()
        # if the isbn number is not valid
        if bookInfo["totalItems"] == 0:
            return apology("Book is not valid", 400)
        listAuthors = bookInfo["items"][0]["volumeInfo"]["authors"]
        # deals with multiple authors
        author = listAuthors[0]
        for person in listAuthors[1:]:
            author = author + ", " + person
        bookUsd = usd(float(request.form.get("price")))
        try:
            bookId = db.execute("INSERT INTO books (title, author, quality, price, usd, seller_id, isbn, language) VALUES(:title, :author, :quality, :price, :usd, :seller_id, :isbn, :language)",
                                title=bookInfo["items"][0]["volumeInfo"]["title"] + ": " + bookInfo["items"][0]["volumeInfo"]["subtitle"], author=author, quality=request.form.get("quality"), price=request.form.get("price"), usd=bookUsd, seller_id=session["user_id"], isbn=isbn, language=bookInfo["items"][0]["volumeInfo"]["language"])
        # if the book does not have a subtitle
        except:
            bookId = db.execute("INSERT INTO books (title, author, quality, price, usd, seller_id, isbn, language) VALUES(:title, :author, :quality, :price, :usd, :seller_id, :isbn, :language)",
                                title=bookInfo["items"][0]["volumeInfo"]["title"], author=author, quality=request.form.get("quality"), price=request.form.get("price"), usd=bookUsd, seller_id=session["user_id"], isbn=isbn, language=bookInfo["items"][0]["volumeInfo"]["language"])
        try:
            # source on uploading files with Flask: http://flask.pocoo.org/docs/0.12/patterns/fileuploads/
            file = request.files["coverimage"]
            # creates a new name for the file depending on the book's id
            # source: https://python-reference.readthedocs.io/en/latest/docs/str/rsplit.html
            coverFileName = str(bookId) + "." + file.filename.rsplit('.', 1)[1]
            # stores the cover name in the database
            db.execute("UPDATE books SET cover=:cover WHERE id=:bookid", cover=coverFileName, bookid=bookId)
            # saves the cover image under the new name
            filename = (os.path.join(app.config["UPLOAD_FOLDER"], coverFileName))
            file.save(filename)
         # if the user's cover file is invalid or if the user did not submit a cover image
        except:
            pass
        return redirect("/")


@app.route("/removeSell", methods=["POST"])
@login_required
def removeSell():
    """Lets user remove a book they put up for sale"""
    bookid = request.form.get("bookId")
    cover = db.execute("SELECT cover from books WHERE id=:bookid", bookid=bookid)[0]["cover"]
    # removes the book cover image or "pass" if a cover image never existed
    try:
        # source: https://www.dummies.com/programming/python/how-to-delete-a-file-in-python/
        os.remove("./static/cover/" + cover)
    except:
        # source: https://stackoverflow.com/questions/574730/python-how-to-ignore-an-exception-and-proceed
        pass
    # source: https://www.w3schools.com/sql/sql_delete.asp
    # deletes the book
    db.execute("DELETE FROM books WHERE id=:bookid", bookid=bookid)
    return redirect("/")


@app.route("/returnBook", methods=["POST"])
@login_required
def returnBook():
    """Lets a user return a book they bought"""
    bookid = request.form.get("bookId")
    # sets the book to "not sold"
    db.execute("UPDATE books SET buyer_id=NULL, sold=0 WHERE id=:bookid", bookid=bookid)
    return redirect("/")


@app.route("/profile", methods=["GET"])
@login_required
def profile():
    """Lets user see their user profile (username, email, college)"""
    person = db.execute("SELECT college, user, email from users WHERE id=:user", user=session["user_id"])[0]
    return render_template("profile.html", person=person)
