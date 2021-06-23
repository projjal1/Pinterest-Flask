from os import error
import re
from flask import Flask, render_template, session, request, redirect
from flask.helpers import url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.operators import distinct_op
from PIL import Image
import random

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

class user_slugs(db.Model):
    id = db.Column('slug_id', db.Integer, primary_key = True)
    user_id = db.Column(db.Integer)
    bio = db.Column(db.String(1000))
    website = db.Column(db.String(100))

class pin_category(db.Model):
    id = db.Column('category_id', db.Integer, primary_key=True)
    name = db.Column(db.String(200))

#db.create_all()

#Routing functions
@app.route('/', defaults={'category': "All"})
@app.route('/<category>')
def index(category="All"):
    if category=="All":
        record_images=images.query.all()
    else:
        record_images=images.query.filter_by(fields=category).all()

    random.shuffle(record_images)

    if "username" in session:
        return render_template("home.html", display_nm=session["username"],images_list=record_images)
    else:
        return render_template("home.html", display_nm="Author",images_list=record_images)


#TODO Return Similar images to shown image

@app.route('/view/<photo_id>')
def view_photo(photo_id):
    if "username" not in session:
        nm="Author"
    else:
        nm=session["username"]
    


    record_images=images.query.filter_by(id=photo_id).all()
    user_id=record_images[0].user_id
    user_details=users.query.filter_by(id=user_id).all()
    img_obj=images.query.filter_by(user_id=user_id).all()
    random.shuffle(img_obj)

    return render_template("view-photo.html",display_nm=nm, img_data=record_images[0], user_data=user_details[0], 
    images_list=img_obj[:20])

@app.route('/author',methods=["GET","POST"])
def profile():
    nm=session["username"]

    if request.method=="GET":
        return render_template("profile.html",display_nm=nm)
    elif request.method=="POST":
        #Get input infos
        bio=request.form.get("bio")
        website=request.form.get("url")
        img=request.files["img"]
        read_img=Image.open(img)

        #Query 
        user_obj=users.query.filter_by(email=session["email"],name=session["username"]).all()
        user_id=user_obj[0].id

        read_img.save("static/portal_images/user"+str(user_id)+".jpg")

        links=website
        if 'www.' not in links:
            links='www.'+links
        if 'https' not in links or 'http' not in links:
            links='https://'+links

        #Create slug object
        obj=user_slugs(user_id=user_id,bio=bio,website=links)
        db.session.add(obj)
        db.session.commit()

        return redirect(url_for('index'))


#Action means whether it's for login or for view of profile 
#Action 0 means to login and 1 means login to view profile

@app.route(r'/profile', defaults={'profile_email': "Default", "action":0})
@app.route(r'/profile/<profile_email>/<action>')
def profile_view(profile_email,action):
    if "username" not in session:
        nm="Author"
        if action==0:
            return render_template("sign.html",display_nm=nm)
        else:
            return render_template("sign.html",display_nm=nm,error="You need to log in to view profile of users.")
    else:
        nm=session["username"]
        
        if profile_email=="Default":
            email=session["email"]
        else:
            email=profile_email
        obj=users.query.filter_by(email=email).all()
        user_id=obj[0].id
        slug_obj=user_slugs.query.filter_by(user_id=user_id).all()
        img_obj=images.query.filter_by(user_id=user_id).all()
        
        return render_template("profile_view.html",display_nm=nm,user_data=obj[0],slug_data=slug_obj[0],images_list=img_obj
        ,img_count=len(img_obj))


@app.route(r'/post',methods=["GET","POST"])
def post():
    if request.method=="GET":
        nm=session["username"]
        cat_records=pin_category.query.all()
        return render_template("post.html",display_nm=nm,categories=cat_records)
    elif request.method=="POST":
        nm=session["username"]
        title=request.form.get("iname")
        desc=request.form.get("desc")
        field=request.form.get("cat")
        links=request.form.get("links")
        img=request.files["img"]

        if 'www.' not in links:
            links='www.'+links 
        if 'https' not in links or 'http' not in links:
            links='https://'+links

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

        cat_records=pin_category.query.all()
        return render_template("post.html",display_nm=nm, success="Image Saved",categories=cat_records)

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
        cat_records=pin_category.query.all()
        return render_template("signup.html",display_nm=nm,categories=cat_records)
    elif request.method == "POST":
        fname=request.form.get("fname")
        lname=request.form.get("lname")
        full_name=fname+" "+lname
        email=request.form.get("email")
        pwd=request.form.get("pwd")
        interest_list=request.form.getlist("int")

        new_string=""
        for ls in interest_list:
            new_string=new_string+ls+","
        
        user_obj = users(name=full_name, email=email, password=pwd, interests=new_string[:-1])
        db.session.add(user_obj)
        db.session.commit()
            
        #Set session object 
        session["username"]=full_name
        session["email"]=email
        return redirect(url_for("profile"))
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