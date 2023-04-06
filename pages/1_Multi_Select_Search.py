import streamlit as st
import pandas as pd
import requests
import re
import numpy as np
import time
import folium
from streamlit_folium import st_folium
from PIL import Image
from io import BytesIO
import time
from azure.storage.blob import BlobServiceClient
import logging


logger = logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)

connection_string = st.secrets["database_connection"]["connection_string"]
container_name = st.secrets["database_connection"]["container_name"]
masterSearchFileName = st.secrets["database_connection"]["masterSearchFileName"]
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container=container_name)

downlodData = container_client.download_blob(masterSearchFileName).readall()
keydict = pd.read_json(BytesIO(downlodData), dtype={"Search":str, "Latitude":np.float32, "Longitude":np.float32, "Time":np.float32, "Key":str})


headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36", 
			"Accept-Encoding":"gzip, deflate",
			"Accept-Language":"en,en-IN;q=0.9,en-US;q=0.8,hi;q=0.7",
			"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9", 
			"DNT":"1",
			"Connection":"close", 
			"Upgrade-Insecure-Requests":"1"}
zoom = 16.01
delta_lat = 0.027
delta_long = delta_lat/np.cos(delta_lat*np.pi/180)
coordinates = ""

def displayBackend(df_):
    for i in range(10 if len(df_)>=10 else len(df_)):
        name = df_.loc[i, "Descrs"]
        link = "https://www.google.co.in/maps/search/" + df_.loc[i, "Descrs"].replace(" ", "+")
        st.write(f"""{i+1}. [{name}]({link})  
            **Actual Rating** : {df_.loc[i, "Rating"]}  
            **Raters** : {df_.loc[i, "Raters"]}  
            **Scaled Rating** : {round(df_.loc[i, "Scaled Rating"], 2)}  
            **Distance Scaled Rating** : {round(df_.loc[i, "Scaled Dist Rating"], 2)}  
            **Displacement** : {round(df_.loc[i, "Dist"], 2)}  
            """)
        # link = "https://www.google.co.in/search?q=google+maps+" + df.iloc[i, 0].replace(" ", "+") + "&tbm=isch"
        # html_text = requests.get(link, headers=headers).text
        imgstr = str(df_.loc[i, "ImgLinks"])
        imglinks = imgstr.split(",")[:4] if "," in str(df_.loc[i, "ImgLinks"]) else []
        if len(imglinks) > 0:
            cols = st.columns(len(imglinks))
            for i in range(len(imglinks)):
                # cols[i].image(imglinks[i]+"=w200-h200-k-no")
                r = requests.get(imglinks[i]+"=w150-h150-k-no")
                if r.status_code == 200:
                    img = Image.open(BytesIO(r.content))
                    width, height = img.size
                    resize_len = width if width >= height else height
                    img = img.resize((resize_len, resize_len))
                    cols[i].image(img)
                else:
                    continue
    

def displayData(df_):
    
    tab1, tab2 = st.tabs(["Best Places by Rating", "Data"])
    
    with tab2:
        st.dataframe(df_)
    
    with tab1:
        df_ = df_.sort_values("Scaled Rating", ascending=False).reset_index(drop=True)
        df_.to_csv("result.csv", index=False)
        displayBackend(df_)


locations = pd.read_csv("worldcities.csv")

search_for = st.text_input('Search For:', "Restaurant")

selected_cities = (st.multiselect("In:", locations["City_list"], 
                                  default=['Delhi, Delhi, India',
                                           'Mumbai, Mahārāshtra, India',
                                           'Kolkata, West Bengal, India',
                                           'Bangalore, Karnātaka, India',
                                           'Chennai, Tamil Nādu, India',
                                           'Hyderabad, Telangana, India',
                                           'Pune, Mahārāshtra, India']))

coordinate_list = (locations.loc[locations["City_list"].isin(selected_cities), ["lat", "lng"]].astype(str))
coordinate_list = (coordinate_list["lat"] + ", " + coordinate_list["lng"]).values

if (len(coordinate_list) != 0) and (search_for != ""):

    st.text("Search for {0} near: \n{1}".format(search_for,"\n".join(coordinate_list)))

    clicked = st.button("Search")

    if clicked == True:
        
        df_combined = pd.DataFrame([], columns=['Descrs', 'Rating', 'Raters', 'Latitude', 'Longitude', 'ImgLinks'])
        
        loopcounter = 0
        progbar = st.progress(loopcounter)
        
        for coordinates in coordinate_list:
            latitude = float(coordinates.split(",")[0])
            longitude = float(coordinates.split(",")[1])

            search_for = search_for.strip().lower().replace(" ", "+")
            
            keylist = (keydict.loc[(keydict["Search"]==search_for) & 
                            ((keydict["Latitude"]-latitude).abs() <= delta_lat) & 
                            ((keydict["Longitude"]-longitude).abs() <= delta_long), "Key"])
            
            
            key = keylist.values[0] if len(keylist.values)>0 else "None"
            
            
            if ((key != "None")):
                
                resultFileName = "projects/mapCrawler/data/result/"+key+".json"
                downlodData = container_client.download_blob(resultFileName).readall()
                df = (pd.read_json(BytesIO(downlodData), 
                                    dtype={"Descrs":str,"Rating":float,"Raters":int, "Latitude":float,"Longitude":float,
                                        "ImgLinks":str,"Scaled Rating":float,"Dist":float,"Scaled Dist Rating":float
                                        }
                                    ))
                loopcounter += 100/(len(coordinate_list))
                progbar.progress(int(loopcounter))

                
            if ((key == "None")):

                latlonglist = [(latitude+i, longitude+j) for i in [k*delta_lat for k in range(-2, 3)] 
                        for j in [k*delta_long for k in range(-2, 3)]]

                queryData = []
                
                restime = time.time()

                for (lat, long) in latlonglist:
                    
                    link = ("https://www.google.co.in/maps/search/" + search_for + "/@" + str(round(lat, 7)) + "," + 
                        str(round(long, 7)) + "," + str(zoom)+ "z/data=!4m4!2m3!5m1!4e3!6e5?hl=en&authuser=0")

                    html_text = requests.get(link, headers=headers).text
                        
                    startList = [m.start() for m in re.finditer(r"\d+ reviews", html_text)]
                    if len(startList) == 0:
                        continue
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
                        for j in chunckedlist[:100]:
                            if (j.startswith('\\"0x')) and (found==0):
                                found = 1
                                partCounter = counter
                            if (name=="") and (j.startswith('\\"') and (not (j.endswith('\\"') or j.endswith('\\"]')))):
                                name = j
                            elif (name != "") and (not j.endswith('\\"')):
                                name = name + j
                            elif (name != "") and (j.endswith('\\"')):
                                name = name + j
                                if len(name) >= len(prevname):
                                    prevname = name
                                    name = ""
                            counter += 1
                        descrs = prevname.replace("\\", '').replace('"', '')
                        loclat = float(re.findall("-?\d+\.?\d*", chunckedlist[partCounter-2])[0])
                        loclong = float(re.findall("-?\d+\.?\d*", chunckedlist[partCounter-1])[0])
                        if ((abs(abs(loclat)-abs(latitude)) > 0.1) or (abs(abs(loclong)-abs(longitude)) > 0.1)):
                            continue
                        imglinks = ",".join([j for j in set(re.findall("https://lh5[^,\\\\]+", i)) if "/p/" in j])
                        queryData.append([descrs, rating, raters, loclat, loclong, imglinks])
                    loopcounter += 100/(25*len(coordinate_list))
                    progbar.progress(int(loopcounter))

                    
                df = pd.DataFrame(queryData, columns=['Descrs', 'Rating', 'Raters', 'Latitude', 'Longitude', 'ImgLinks'])
                df = df.drop_duplicates(subset=['Descrs', 'Rating', 'Raters', 'Latitude', 'Longitude'])

                df['Scaled Rating'] = df['Rating']*(1 - np.power(1.25, -1*np.sqrt(df['Raters'])))

                df["Dist"] = (np.sqrt((((df['Latitude']-latitude)*111.3188)**2) + 
                        (((df['Longitude']-longitude)*np.cos(latitude*0.0174)*111.3188)**2)))

                df["Scaled Dist Rating"] = df["Scaled Rating"]*(1 - np.power(1.25, -11.1/df["Dist"]))

                key = str(restime).split(".")[0]
                keydict.loc[len(keydict), ["Search", "Latitude", "Longitude", "Time", "Key"]] = [search_for, latitude, longitude, restime, key]
                keydict = keydict.sort_values(["Time", "Search"], ascending=False)
            
                resultFileName = "projects/mapCrawler/data/result/"+key+".json"
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=resultFileName)
                _ = blob_client.upload_blob(df.to_json(), overwrite=True)
            
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=masterSearchFileName)
                _ = blob_client.upload_blob(keydict.to_json(), overwrite=True)
                
            df_combined = pd.concat([df_combined, df])

        displayData(df_combined)