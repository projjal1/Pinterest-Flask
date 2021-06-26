from os import error
import os
import re
from flask import Flask, render_template, session, request, redirect, send_from_directory
from flask.helpers import url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.operators import distinct_op
from PIL import Image
import random
import pandas as pd
import numpy as np
from sklearn.decomposition import TruncatedSVD
import pickle
from collections import Counter
from datetime import datetime

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

class track_visits(db.Model):
    id = db.Column('visit_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    img_id = db.Column(db.Integer)

class admin_post(db.Model):
    id = db.Column('admin_id', db.Integer, primary_key=True)
    advertisement_title = db.Column(db.String(100))
    thought_title = db.Column(db.String(100))
    advertisement_link = db.Column(db.String(100))
    thought_link = db.Column(db.String(100))
    date = db.Column(db.String(100))

class follow_user(db.Model):
    id = db.Column('follow_id', db.Integer, primary_key=True)
    user_email = db.Column(db.String(100))
    follower_email = db.Column(db.String(100))

class saved_pins(db.Model):
    id = db.Column('save_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    img_id = db.Column(db.Integer)

#Run only to create initial .sqlite database 
#db.create_all()


#Data extractors 
def extract_users():
    records=users.query.all()
    id,email,interests=[],[],[]
    for rec in records:
        var_id,var_name=rec.id,rec.email
        for interest in rec.interests.split(","):
            id.append(var_id)
            email.append(var_name)
            interests.append(interest)

    df=pd.DataFrame({"user_id":pd.Series(id),"name":pd.Series(email),"category":pd.Series(interests),"flag":pd.Series(np.ones(len(email)))})
    return df

def extract_images():
    records=images.query.all()
    id,title,fields,user_ids=[],[],[],[]
    for rec in records:
        id.append(rec.id)
        title.append(rec.title)
        fields.append(rec.fields)
        user_ids.append(rec.user_id)

    df=pd.DataFrame({"img_id":pd.Series(id),"title":pd.Series(title),"category":pd.Series(fields),"user_id":pd.Series(user_ids),"img_flag":pd.Series(np.ones(len(title)))})
    return df

def extract_tracks():
    records=track_visits.query.all()
    id,user_ids,img_ids=[],[],[]
    for rec in records:
        id.append(rec.id)
        user_ids.append(rec.user_id)
        img_ids.append(rec.img_id)

    df=pd.DataFrame({"visit_id":pd.Series(id),"user_id":pd.Series(user_ids),"img_id":pd.Series(img_ids),"visits":pd.Series(np.ones(len(id)))})
    return df 

def extract_category():
    records=pin_category.query.all()
    id,name=[],[]
    for rec in records:
        id.append(rec.id)
        name.append(rec.name)

    df=pd.DataFrame({"cat_id":pd.Series(id),"category":pd.Series(name)})
    return df

#calls to compute ratings crosstab matrix and perform Pearson Correlation
#user-user similarity find out
def compute_user_similarity():
    user_data=extract_users()
    image_data=extract_images()
    track_data=extract_tracks()
    category_data=extract_category()

    #user_merge_category=pd.merge(user_data[["name","category"]],category_data[["category"]],on="category")
    user_merge_category=pd.merge(user_data[["name","category","flag"]],category_data[["category"]],on="category")
    user_category = user_merge_category.pivot_table(values='flag', index='name', columns='category', fill_value=0)
    combined_dataset=pd.merge(user_data[["user_id","name"]],image_data[["img_id","user_id","category","img_flag"]],on="user_id")
    user_images = combined_dataset.pivot_table(values= 'img_flag', index='name', columns='category', fill_value=0)
    track_images=pd.merge(image_data[['img_id','title']],track_data[['img_id','user_id']],on="img_id")
    track_user_images=pd.merge(track_images,user_data[["user_id","name"]],on="user_id")

    final_set=pd.merge(user_category,user_images,on="name")
    from sklearn.decomposition import TruncatedSVD

    #generate SVD matrix
    SVD = TruncatedSVD(n_components=5, random_state=17)
    resultant_matrix = SVD.fit_transform(final_set)
    #Computing similarity scores
    corr_mat = np.corrcoef(resultant_matrix)
    import pickle
    # save array
    with open('data-mining/user-corr.pkl','wb') as file:
        pickle.dump(corr_mat,file)
    # save track_data
    with open('data-mining/track_data.pkl','wb') as file:
        pickle.dump(track_user_images,file)
    # save final set 
    with open("data-mining/final_set.pkl",'wb') as file:
        pickle.dump(final_set,file)

#compute_user_similarity()
#Function to return images based on user-user collaborative filtering
def call(nm):
    with open('data-mining/final_set.pkl','rb') as file:
        final_set=pickle.load(file)
    with open('data-mining/user-corr.pkl','rb') as file:
        corr_mat=pickle.load(file)
    with open('data-mining/track_data.pkl','rb') as file:
        track_user_images=pickle.load(file)

    threshold=0.3
    user_list=list(final_set.index)

    idx=user_list.index(nm)
    user_select=Counter()
    
    itr=0
    for score in corr_mat[idx]:
        if score>0.98 or score<threshold:
            itr+=1
        else:
            user_select[itr]=score
            itr+=1

    #Common users
    common_users=5    #Change it to generate more data

    image_names,ids=[],[]
    for k,u in user_select.most_common(common_users):
        email=user_list[k]
        row=track_user_images[track_user_images["name"]==email]
        
        img_names=row.title.values
        id_imgs=row.img_id.values
        
        for i in range(len(img_names)):
            nm=img_names[i]
            idsers=id_imgs[i]
            if nm in image_names:
                continue 
            else:
                image_names.append(nm)
                ids.append(idsers)

    ls_objs=[]
    for var in ids:
        print(id,images.query.filter_by(id=str(var)).all())
        ls_objs.append(images.query.filter_by(id=str(var)).all()[0])
    return ls_objs

#Admin post 
@app.route("/admin_post",methods=["GET","POST"])
def admin_listing():
    if request.method=="GET":
        return render_template("admin_post.html",display_nm="Admin")
    else:
        advertisment_title=request.form.get('iname2')
        advertisment_link=request.form.get('link2')
        thought_title=request.form.get('iname1')
        thought_link=request.form.get('link1')
        img_path_adv=request.files['img2']
        img_path_thought=request.files['img1']

        #Creating date-string 
        dt=datetime.now()
        format=dt.strftime("%d %B, %Y")

        admin_obj=admin_post(advertisement_link=advertisment_link,advertisement_title=advertisment_title,thought_title=thought_title,thought_link=thought_link,date=format)
        db.session.add(admin_obj)
        db.session.commit()


        img1=Image.open(img_path_adv)
        img2=Image.open(img_path_thought)

        #retreive id 
        admin_rec=admin_post.query.filter_by(date=format).all()
        admin_rec=admin_rec[0]
        admin_id=admin_rec.id
        
        img1.save('static/admin_promo/adv'+str(admin_id)+".jpg")
        img2.save('static/admin_promo/thought'+str(admin_id)+".jpg")

        return redirect(url_for('index'))


#Routing functions
@app.route('/', defaults={'category': "All"})
@app.route('/<category>')
def index(category="All"):
    if category=="All" and "email" not in session:
        record_images=images.query.all()
    elif category=="All" and "email" in session:
        if session["username"]!="Admin":
            record_images=call(session["email"])
        else:
            record_images=images.query.all()[-5:]
    else:
        record_images=images.query.filter_by(fields=category).all()

    random.shuffle(record_images)

    if "username" in session:
        return render_template("home.html", display_nm=session["username"],images_list=record_images)
    else:
        return render_template("home.html", display_nm="Author",images_list=record_images)


@app.route('/follow/<email>',methods=["POST"])
def user_follow_action(email):
    if request.method=="GET":
        return redirect(url_for('index'))

    if "username" not in session:
        return render_template("sign.html",display_nm="Author",error="You need to log in to view profile of users.")

    u_email=session["email"]
    obj=follow_user(user_email=email,follower_email=u_email)
    db.session.add(obj)
    db.session.commit()

    return redirect(url_for('profile_view',profile_email=email,action=1))

@app.route('/today')
def exclusive():
    if "username" in session:
        nm=session["username"]
    else:
        nm="Author"
    
    listing_images=admin_post.query.all()[::-1]
    return render_template("latest_uploaded.html",display_nm=nm,images_list=listing_images)

#Save pins
@app.route('/save_pins/<img_id>')
def save_pins(img_id):
    if "username" not in session:
        return render_template("sign.html",display_nm="Author",error="You need to log in to save images.")
    
    #Save into db
    user_rec=users.query.filter_by(email=session["email"]).all()
    obj=saved_pins(user_id=user_rec[0].id,img_id=img_id)
    db.session.add(obj)
    db.session.commit ()

    return redirect(url_for('view_photo',photo_id=img_id))

@app.route('/view/<photo_id>', methods=["POST","GET"])
def view_photo(photo_id):
    if request.method=="POST":
        #Append dir path
        downloads = os.path.join(app.root_path, 'static/portal_images/')
        # Returning file from appended path
        return send_from_directory(directory=downloads, path=str(photo_id)+".jpg")

    if "username" not in session:
        nm="Author"
    else:
        nm=session["username"]
        if nm!="Admin":
            #Track visit 
            user_visited=users.query.filter_by(email=session["email"]).all()
            visit_obj = track_visits(user_id=user_visited[0].id, img_id=photo_id)
            db.session.add(visit_obj)
            db.session.commit()
    
    record_images=images.query.filter_by(id=photo_id).all()
    user_id=record_images[0].user_id
    user_details=users.query.filter_by(id=user_id).all()
    img_obj=images.query.filter_by(fields=record_images[0].fields).all()
    img_obj.pop(img_obj.index(record_images[0]))
    random.shuffle(img_obj)
    obj_follow=follow_user.query.filter_by(user_email=user_details[0].email).all()
    obj_follow_check=follow_user.query.filter_by(user_email=user_details[0].email, follower_email=session["email"]).all()
    obj_users=users.query.filter_by(email=session["email"]).all()
    obj_save_check=saved_pins.query.filter_by(user_id=obj_users[0].id,img_id=photo_id).all()

    if session["email"]==user_details[0].email:
        flag_follow=0
    elif len(obj_follow_check)>0:
        flag_follow=0
    else:
        flag_follow=1

    if len(obj_save_check)>0:
        flag_save=0
    else:
        flag_save=1

    return render_template("view-photo.html",display_nm=nm, img_data=record_images[0], user_data=user_details[0], 
    images_list=img_obj[:20], follow_count = len(obj_follow), flag_follow_check = flag_follow, flag_save_check=flag_save)

@app.route('/author',methods=["GET","POST"])
def profile():
    nm=session["username"]

    if request.method=="GET":
        return render_template("profile.html",display_nm=nm)
    elif request.method=="":
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

        #Call function to generate updated ratings crosstab
        compute_user_similarity()

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
    elif session["username"]=="Admin":
        return redirect(url_for('index'))
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

        len_posts=len(img_obj)

        #Saved pins images 
        obj_users=users.query.filter_by(email=session["email"]).all()
        obj_saved_pins=saved_pins.query.filter_by(user_id=obj_users[0].id).all()

        for each in obj_saved_pins:
            img_id=each.id
            rec=images.query.filter_by(id=img_id).all()[0]
            if rec not in img_obj:
                img_obj.append(rec)

        obj_follow=follow_user.query.filter_by(user_email=profile_email).all()
        obj_following=follow_user.query.filter_by(follower_email=email).all()
        
        return render_template("profile_view.html",display_nm=nm,user_data=obj[0],slug_data=slug_obj[0],images_list=img_obj
        ,img_count=len_posts,follow_count=len(obj_follow),following_count=len(obj_following))


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

        #Updated ratings crosstab matrix
        compute_user_similarity()

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


        #Login explicitly stated
        if email=="administrator@pinterest.com" and pwd=="admin":
            session["email"]="administrator@pinterest.com"
            session["username"]="Admin"
            return redirect(url_for("index"))

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