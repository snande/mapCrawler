import streamlit as st
import pandas as pd
import requests
import re
import numpy as np
import time
import folium
from streamlit_folium import st_folium

def displayData(df):
    for i in range(10):
        name = df.iloc[i, 0]
        link = "https://www.google.co.in/maps/search/" + df.iloc[i, 0].replace(" ", "+")
        st.write(f"""{i+1}. [{name}]({link})  
                **Actual Rating** : {df.iloc[i, 1]}  
                **Raters** : {df.iloc[i, 2]}  
                **Scaled Rating** : {round(df.iloc[i, 5], 2)}  
                **Distance Scaled Rating** : {round(df.iloc[i, 7], 2)}  
                **Displacement** : {round(df.iloc[i, 6], 2)}  
                """)
        link = "https://www.google.co.in/search?q=google+maps+" + df.iloc[i, 0].replace(" ", "+") + "&tbm=isch"
        html_text = requests.get(link, headers=headers).text
        imglinks = re.findall("http[^,]*jpe?g", html_text)[:5]
        if len(imglinks) > 0:
            cols = st.columns(len(imglinks))
            for i in range(len(imglinks)):
                cols[i].image(imglinks[i])

def displayMap():
    m = (folium.Map(location=[st.session_state["lat"], st.session_state["lng"]], 
                zoom_start=st.session_state["zoom"], tiles=None))
    tile = folium.TileLayer(
                            tiles = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
                            attr = 'Google',
                            name = 'Google Satellite',
                            overlay = True,
                            control = True
                            ).add_to(m)
    data = st_folium(m, returned_objects=["center", "zoom"], height=400)
    time.sleep(0.7)
    st.session_state["zoom"] = data["zoom"]
    return data

df = pd.read_csv("/Users/snande/Personal/Projects/mapCrawler/worldcities.csv")

if "lat" not in st.session_state:
    st.session_state["lat"] = 22.59
    st.session_state["lng"] = 79.75
    st.session_state["zoom"] = 4

search_for = st.text_input('Search For:', "Restaurant")
col1, col2 = st.columns([1,3])

with col1:
    countrylist = sorted(df["country"].unique())
    country = st.selectbox("Country", countrylist, index=93)
    statelist = sorted(df.loc[df["country"]==country, "admin_name"].unique())
    state = st.selectbox("State", statelist)
    citylist = sorted(df.loc[(df["country"]==country) & (df["admin_name"]==state), "city_ascii"].unique())
    city = st.selectbox("City", citylist)
    lat, lng = (df.loc[(df["country"]==country) & (df["admin_name"]==state)& (df["city_ascii"]==city), 
                        ["lat", "lng"]].iloc[0])
    st.session_state["lat"] = lat
    st.session_state["lng"] = lng

with col2:
    st_data = displayMap()

search_near = col1.text_input("Near", value = f"{round(st_data['center']['lat'], 2)}, {round(st_data['center']['lng'], 2)}")
clicked = col1.button("Search")

if (clicked == True) and (search_for != ""):

    latitude, longitude = search_near.split(",")
    try:
        latitude = float(latitude)
        longitude = float(longitude)

        search_for = search_for.replace(" ", "+")

        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36", 
                    "Accept-Encoding":"gzip, deflate",
                    "Accept-Language":"en,en-IN;q=0.9,en-US;q=0.8,hi;q=0.7",
                    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9", 
                    "DNT":"1",
                    "Connection":"close", 
                    "Upgrade-Insecure-Requests":"1"}

        if search_near != "":

            zoom = 16.01
            delta_lat = 0.027
            delta_long = delta_lat/np.cos(delta_lat*np.pi/180)

            latlonglist = [(latitude+i, longitude+j) for i in [k*delta_lat for k in range(-2, 3)] 
                            for j in [k*delta_long for k in range(-2, 3)]]

            queryData = []
            

            loopcounter = 0

            progbar = st.progress(loopcounter)

            for (lat, long) in latlonglist:
                    
                    link = ("https://www.google.co.in/maps/search/" + search_for + "/@" + str(round(lat, 7)) + "," + 
                            str(round(long, 7)) + "," + str(zoom)+ "z/data=!4m4!2m3!5m1!4e3!6e5?hl=en&authuser=0")

                    html_text = requests.get(link, headers=headers).text

                    startList = [m.start() for m in re.finditer(r"\d+ reviews", html_text)]
                    strchunks = [html_text[startList[i]:startList[i+1]] for i in range(0, len(startList)-1)]
                    strchunks.append(html_text[startList[-1]:])

                    for i in strchunks:
                            chunckedlist = i.split(",")
                            raters = int(re.findall("\d+", chunckedlist[7])[0])
                            if raters < 30:
                                    continue
                            rating = float(chunckedlist[6])
                            if rating < 4.0:
                                    continue

                            name = ""
                            prevname = ""
                            namelist = []
                            counter = 0
                            found = 0
                            for i in chunckedlist[:100]:
                                    if (i.startswith('\\"0x')) and (found==0):
                                            found = 1
                                            partCounter = counter
                                    if (name=="") and (i.startswith('\\"') and (not (i.endswith('\\"') or i.endswith('\\"]')))):
                                            name = i
                                    elif (name != "") and (not i.endswith('\\"')):
                                            name = name + i
                                    elif (name != "") and (i.endswith('\\"')):
                                            name = name + i
                                            if len(name) >= len(prevname):
                                                    prevname = name
                                                    name = ""
                                    counter += 1
                            descrs = prevname.replace("\\", '').replace('"', '')
                            loclat = float(re.findall("-?\d+\.?\d*", chunckedlist[partCounter-2])[0])
                            loclong = float(re.findall("-?\d+\.?\d*", chunckedlist[partCounter-1])[0])
                            if ((abs(abs(loclat)-abs(latitude)) > 0.1) or (abs(abs(loclong)-abs(longitude)) > 0.1)):
                                    continue
                            queryData.append([descrs, rating, raters, loclat, loclong])
                    loopcounter += 100/25
                    progbar.progress(int(loopcounter))

                    

            df = pd.DataFrame(queryData, columns=['Descrs', 'Rating', 'Raters', 'Latitude', 'Longitude'])
            df = df.drop_duplicates()

            df['Scaled Rating'] = df['Rating']*(1 - np.power(1.25, -1*np.sqrt(df['Raters'])))
            df = df.sort_values("Scaled Rating", ascending=False)

            df["Dist"] = (np.sqrt((((df['Latitude']-latitude)*111.3188)**2) + 
                                (((df['Longitude']-longitude)*np.cos(latitude*0.0174)*111.3188)**2)))

            df["Scaled Dist Rating"] = df["Scaled Rating"]*(1 - np.power(1.25, -11.1/df["Dist"]))

            df.to_csv("result.csv", index=False)


            st.subheader("Best Places by Rating")
            displayData(df)

            st.subheader("Best Places by Distance")
            df = df.sort_values("Scaled Dist Rating", ascending=False)
            displayData(df)

    except:
        st.write("Incorrect location input")