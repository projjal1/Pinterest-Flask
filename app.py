import re
from flask import Flask, render_template, session, request, redirect
from flask.helpers import url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.operators import distinct_op
from PIL import Image

# Flask app configs
app=Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user-data.sqlite3'
app.secret_key = 'soverysecret'

#Database 
db = SQLAlchemy(app)
class users(db.Model):
    id = db.Column('user_id', db.Integer, primary_key = True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password = db.Column(db.String(100))
    interests = db.Column(db.String(200))

class images(db.Model):
    id = db.Column('image_id', db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    fields = db.Column(db.String(300))
    description = db.Column(db.String(1000))
    links = db.Column(db.String(200))
    user_id  = db.Column(db.Integer)

#db.create_all()

#Routing functions
@app.route('/')
def index():
    if "username" in session:
        return render_template("home.html", display_nm=session["username"])
    else:
        return render_template("home.html", display_nm="Author")

@app.route('/author')
def profile():
    if "username" not in session:
        nm="Author"
        return render_template("sign.html",display_nm=nm)


@app.route('/post',methods=["GET","POST"])
def post():
    if request.method=="GET":
        nm=session["username"]
        return render_template("post.html",display_nm=nm)
    elif request.method=="POST":
        nm=session["username"]
        title=request.form.get("iname")
        desc=request.form.get("desc")
        field=request.form.get("cat")
        links=request.form.get("links")
        img=request.files["img"]

        print(field)

        #Get user-id 
        record=users.query.filter_by(email=session["email"]).all()
        user_id=record[0].id

        #Save in Database
        image_obj = images(title=title, description=desc, fields=field, links=links, user_id=user_id)
        db.session.add(image_obj)
        db.session.commit()


        #Fetch image-id 
        record=images.query.filter_by(title=title, description=desc, fields=field, links=links, user_id=user_id).all()
        image_id=record[0].id
        image=Image.open(img)
        image.save("static/portal_images/"+str(image_id)+".jpg")

        return render_template("post.html",display_nm=nm, success="Image Saved")

@app.route('/logout')
def logout():
    session.pop("username")
    session.pop("email")
    return redirect(url_for("index"))

@app.route('/register', methods=["GET","POST"])
def register():
    if "username" in session:
        nm=session["username"]
    else:
        nm="Author"

    if request.method == "GET":
        return render_template("signup.html",display_nm=nm)
    elif request.method == "POST":
        fname=request.form.get("fname")
        lname=request.form.get("lname")
        full_name=fname+" "+lname
        email=request.form.get("email")
        pwd=request.form.get("pwd")
        interest_list=request.form.getlist("int")

        for interest in interest_list:
            user_obj = users(name=full_name, email=email, password=pwd, interests=interest)
            db.session.add(user_obj)
            db.session.commit()
            
        #Set session object 
        session["username"]=full_name
        session["email"]=email
        return redirect(url_for("index"))
    else:
        return "404, Access not Allowed!"

@app.route('/login', methods=["GET","POST"])
def login():
    if "username" in session:
        nm=session["username"]
    else:
        nm="Author"

    if request.method == "GET":
        return render_template("signin.html",display_nm=nm)
    elif request.method == "POST":
        email=request.form.get("email")
        pwd=request.form.get("pwd")
        record=users.query.filter_by(email=email, password=pwd).all()
        
        if len(record)>0:
            full_name=record[0].name
            session["username"] = full_name
            session["email"] = email
            return redirect(url_for("index"))
            
        else:
            return render_template("signin.html",display_nm=nm, error="Wrong email or Password entered!")
    else:
        return "404, Access not Allowed!"


if __name__=="__main__":
    app.run(debug=True, port=8000)