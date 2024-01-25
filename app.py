import sys
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from flask import Flask, request

# Read in Cloud Credentials
firebase_key = eval(open('firebase_key.txt','r').read())
databaseURL = open('databaseURL.txt','r').read()

# Connecting
cred = credentials.Certificate(firebase_key)
firebase_admin.initialize_app(cred, {'databaseURL': databaseURL})

# Initialize App
app = Flask(__name__)

# Dashboard
@app.route('/')
def index():
	print('App was tested')
	sys.stdout.flush()
	return "Madden CFM Exporter V1.0"

# Clear DB
@app.route('/delete')
def delete():
	db.reference().delete()
	return "Data Cleared"

# Team Info
@app.route('/<system>/<leagueId>/leagueteams', methods=['POST'])
def teams(system,leagueId):
	db.reference('data/'+system+'/'+leagueId+'/leagueteams').set(request.json)
	return 'OK', 200

# Team Standings
@app.route('/<system>/<leagueId>/standings', methods=['POST'])
def standings(system,leagueId):
	db.reference('data/'+system+'/'+leagueId+'/standings').set(request.json)
	return 'OK', 200

# Free Agents
@app.route('/<system>/<leagueId>/freeagents/roster', methods=['POST'])
def freeagents(system, leagueId):
	db.reference('data/'+system+'/'+leagueId+'/freeagents').set(request.json)
	return 'OK', 200

# Rosters
@app.route('/<system>/<leagueId>/team/<teamId>/roster', methods=['POST'])
def roster(system, leagueId, teamId):
	db.reference('data/'+system+'/'+leagueId+'/team/'+teamId).set(request.json)
	return 'OK', 200

# Weekly stats
@app.route('/<system>/<leagueId>/week/<weekType>/<weekNumber>/<dataType>', methods=['POST'])
def stats(system, leagueId, weekType, weekNumber, dataType):
	statname = next(k for k,v in request.json.items() if 'List' in k)
	db.reference('data/'+system+'/'+leagueId+'/week/'+weekType+'/'+weekNumber+'/'+dataType+'/'+statname).set(request.json[statname])
	return 'OK', 200

if __name__ == '__main__':
	app.run()
