**SideLine: Analyze matches using AI, no matter the level of play**

SideLine is a pipeline which consists of AI models trained on basketball and football footage to do the boring work of match editing and analysis for you. It takes in any recorded basketball or football match, and spits out coach analytics, player and event highlights

<img width="1792" height="998" alt="image" src="https://github.com/user-attachments/assets/305b2ab6-f9a9-490b-9bb6-1bfe3d726a11" />

You can upload your match recordings and enter simple setup data like the corners of the playing field, ID'ing the players to choose exactly what you want

<img width="2559" height="1374" alt="image" src="https://github.com/user-attachments/assets/cc176546-4504-45c7-a33a-88cb7242bbc6" />

**In return you get:**

**Coach analytics** - Data containing possession for each team, the distance covered by each team, the overall team shape (compactness and formations followed), intensity (how often runs are made? how quickly?) and which space your team most occupies during the recording (the left third, middle third or the right third)

<img width="780" height="1013" alt="image" src="https://github.com/user-attachments/assets/6b30452c-8dbc-4221-be33-fcf37e0581ea" />

Well that was the boring part, if your more into posting highlights online on social media but hate sitting through a 90 minute match making cuts, this repo has you covered!

**Event highlights** - include goals and baskets made, goals and baskets attempted, fast transitions in play, long passes, tackles and steals, stoppages and player to player contacts automatically cut so that you can just drop in the clips however you'd like for content

<img width="2559" height="1368" alt="image" src="https://github.com/user-attachments/assets/e5a27901-53cf-493c-816c-af5fe02e504b" />

However the content doesn't stop there, no player is left out, each player gets their own highlightes (Provided you do the Player ID'ing setup)

**Player highlights** - which includes specific highlights for EACH player (if possible) when they held the ball, tackles they made, passes, shots, interceptions, saves, celebrations, reactions, close contacts

**SO why did I build this?**

I study in DPS Modern Indian School in Qatar, and play football for the team there. I noticed a problem, important matches in football and basketball were HARDLY recorded, sure there were a few photos here and there, but thats not very useful. Currently, the coaches have to trust their eyes and memory to make tactical descisions, and I always hear the student council and the publications club complain whenever it came to actual content posting for any game "Why is there no footage? What will we do with photos?". Even the players felt disheartened that their insane goal, or highlight dunk was never captured. As a result, this project was born, I wanted to help our coaches understand how the team was playing, and also satisfy the needs of content team and our hard working players (3 birds one stone).

<img width="2086" height="1263" alt="image" src="https://github.com/user-attachments/assets/0731a5b5-c8bd-4c30-962a-7e8da4461fef" /> <img width="2023" height="905" alt="image" src="https://github.com/user-attachments/assets/e4df9070-e397-4183-be1c-ac5f76407ae9" />

**How does it work?**

First you submit a match video through the public website, your login and the job state is held in the Supabase Postgres databse, the actual footage you submitted is sent to a Google Drive (my strict requirement for this project was 0 dollars spent). A python agent in local processing computer checks the Supabase and takes each new video it finds in the Frive into a local Fast API backend and runs the computer - vision pipleine on the GPU of your own laptop (provided you set it up locally (check later sections)). The pipeline breaks your clips into frames and detects and tracks player using a custom trained YOLO model and ByteTrack (a true saviour), which tracks the ball with a detector fed into a Kalman filter. Players are sorted into their teams using appearance. Remember how we had to click different points on the field? This was to project each player onto a pitch model to build the coach analytics (heatmaps, formations, territory, possession), the per player highlights (detecting a players involvement) using us to tag each player per clip (to maintain identity). Event highlight reels are created by detecting the position of the ball with respect to the field and how fast the ball moves. Processing stops in between so that we can tag each player with a name. Finally all three results are put into the Drive folder and the user recieves a mail. (After 14 days your materials expire except the one match I have left as a courtesy to the reviewers)

**Some challenges I faced during this project (till now)**

1. The funniest problem I've had is trying to get the model to distinguish a human head from a basketball, I spent 3 days on that, and just decided to retrain the model after classifying and painstakingly labelling 500 images as a head or a basketball (it worked, but randomly heads are still detected as basketballs sometimes)

<img width="967" height="604" alt="image" src="https://github.com/user-attachments/assets/ca030e3b-4f2a-47f2-83de-8e57a40cbed4" />

2. The hardest problem I've had till now (and I still havent solved it properly) is tracking a singular player during an entire match. One shadow, one block and the model thinks a new player suddenly appeared?! Once in a 90 minute game I had 47 different players detected (FYI a football game has 22 players on the pitch). I did solve this cheaply, by putting the work on us humans and asking for a per player tag on each clip the model lost the player (I find this solution disgusting, as it doesn't fix the root problem, I'm not stopping here)

<img width="1798" height="1005" alt="image" src="https://github.com/user-attachments/assets/dc9b18b0-74d4-4c63-a3c3-eac050548fbe" />
Detects the players
<img width="1794" height="1000" alt="image" src="https://github.com/user-attachments/assets/3da41dfd-19ef-47ad-8e66-20c649e709b2" />
Loses a few and when it redetects it logs them as NEW players...

**Tech Stack:**
Computer vision / ML:** Python, Ultralytics YOLO (custom-trained `.pt` models per sport), ByteTrack multi-object tracking, PyTorch 2.11 + CUDA 12.8,OpenCV, NumPy / SciPy, a Kalman filter for ball tracking, ffmpeg (H.264 re-encode for browser-playable clips).**Local backend:** FastAPI + Uvicorn, Pydantic, a SQLite job store, and background worker.**Local agent:** Python (`requests`, `python-dotenv`,`google-auth-oauthlib`) with Windows toast notifications.**Cloud / web:** static HTML/CSS/JS site on Cloudflare Pages; Supabase(Postgres + GoTrue auth + PostgREST); Google Drive (OAuth) as the file relay and email for job notifications.**Testing:** pytest.

**FOR REVIEWERS AND TESTERS**

If you want to try the DEMO and get sample results and data go to **https://sideline-d8c.pages.dev/** and click "See how it works" under the login

<img width="2552" height="1413" alt="Screenshot 2026-07-06 202350" src="https://github.com/user-attachments/assets/89f1791f-081e-4400-a692-4244bdf7b061" />

Go through and follow the instructions of the different setup steps (DEMO only)
If you want to see actual results (based on a Tottenham vs Watford football game) at the end of the DEMO, click the "Open Results" button which will take you to the drive containing real results.

<img width="2559" height="1459" alt="Screenshot 2026-07-06 202701" src="https://github.com/user-attachments/assets/cbe8e511-fb3d-43fa-9be0-9b783ecb6a1b" />

Want to see how to submit a match, or how it looks like for the admin? Use the credentials to login at **https://sideline-d8c.pages.dev/** (**Login: demo@sideline.review   Password: 12345678 **(Extremely secure I'm aware))
<img width="2559" height="1406" alt="image" src="https://github.com/user-attachments/assets/52ecdeaa-1697-4d55-9983-bc8e95c0dc56" />
Once you sign in, you can check the dashboard to see the status of matches submitted for the pipeline, you can click on the "Ready" match to get the same link to the drive for REAL processed data.
To submit a match for the pipeline click the "Submit a match" button at the top and follow the instructions
<img width="2559" height="1450" alt="image" src="https://github.com/user-attachments/assets/904a9cf8-7abf-4c5c-b289-e5b0f0354128" />
For admin view just click "admin" at the top of the page
<img width="2559" height="1443" alt="image" src="https://github.com/user-attachments/assets/e12fe3da-590c-4eec-88b5-7f62544b0fad" />

**But what if you want to run this pipeline on your own GPU on YOUR computer?**
If so follow the steps below exactly

  1. Clone the repo
  ```sh
  git clone https://github.com/Osmiosis/SideLine && cd SideLine 
```
  2. Set up the Python environment (backend + local studio + agent)
```sh
  python -m venv .venv
  .venv\Scripts\activate           # Windows
  pip install -r requirements.txt
```

  3. Run the local studio (processing backend, port 8000)
```sh
  .venv\Scripts\python -m backend.main
```
  4. Run the relay agent (pulls submitted footage, pushes results)
```sh
  .venv\Scripts\python -m agent.run
```
  5. The public site (static, Cloudflare Pages)
```sh
  npx wrangler pages dev site          # local preview
  node --test site/tests/*.test.mjs    # run the site tests
```
Yes we are finally done, but I'm not finished, theres much more to come! Hardware and some more software fixes!

**Declaration of AI USE: EXTENSIVE USE OF CLAUDE CODE**
