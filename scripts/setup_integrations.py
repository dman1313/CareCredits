"""Private local configuration; API keys are never accepted through chat/arguments."""
import getpass
import os
from pathlib import Path
import re
import secrets


def main():
    root=Path(__file__).resolve().parents[1]
    destination=root/'.env'
    content=(destination if destination.exists() else root/'.env.sample').read_text()
    values={}
    for key, label in [('TAVILY_API_KEY','Tavily API key'),('FIREHOSE_MGMT_KEY','Firehose management key (fhm_)'),('MODEL_API_KEY','Nebius/model API key'),('TYPESAFE_API_KEY','TypeSafe / Jev API key'),('GOOGLE_CLIENT_ID','Google OAuth client ID'),('GOOGLE_CLIENT_SECRET','Google OAuth client secret')]:
        value=getpass.getpass(label+' (hidden; blank keeps existing): ').strip()
        if value:
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',value):
                raise SystemExit('Unexpected key format. Configure the server secret directly instead.')
            values[key]=value
    for key,label,pattern in [
        ('MODEL_ID','Model ID from your provider', r'[A-Za-z0-9_./:?=&%#@+~-]+'),
        ('MODEL_WEIGHTS_URL','Official model weights URL', r'[A-Za-z0-9_./:?=&%#@+~-]+'),
        ('MODEL_LICENSE_URL','Official model licence URL', r'[A-Za-z0-9_./:?=&%#@+~-]+'),
        ('MODEL_PUBLISHER','Model publisher', r'[A-Za-z0-9][A-Za-z0-9 ._+/-]{0,80}'),
        ('MODEL_HOST','Model hosting provider', r'[A-Za-z0-9][A-Za-z0-9 ._+/-]{0,80}'),
    ]:
        value=input(label+' (blank keeps existing): ').strip()
        if value:
            if not re.fullmatch(pattern,value):
                raise SystemExit('Unexpected configuration format.')
            values[key]=value
    if input('Have you verified this model has available weights and a suitable licence? [yes/no]: ').strip().lower()=='yes':
        values['MODEL_OPEN_WEIGHT_CONFIRMED']='true'
    for key in ['SCRAPER_SERVICE_TOKEN','POSTGRES_PASSWORD']:
        if not re.search(r'^'+key+r'=\S+',content,re.M):
            values[key]=secrets.token_urlsafe(32)
    for key,value in values.items():
        pattern=r'^'+key+r'=.*$'
        if re.search(pattern,content,re.M):
            content=re.sub(pattern,lambda _:key+'='+value,content,flags=re.M)
        else:
            content+='\n'+key+'='+value+'\n'
    fd=os.open(destination,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:
        os.fchmod(f.fileno(),0o600);f.write(content)
    print('Saved .env privately. Restart services. No live calls have been made.')


if __name__=='__main__':main()
