#!/usr/bin/env python3
"""Protect the existing qa.ltli.ai HTTPS server, with backup and rollback."""
import datetime
import pathlib
import re
import subprocess
import sys
import os


def protect(text):
    # Nginx configuration here is ordinary server blocks; refuse ambiguous input.
    blocks=list(re.finditer(r'(?m)^\s*server\s*\{',text))
    matches=[]
    for block in blocks:
        depth=1;pos=block.end()
        while pos<len(text) and depth:
            char=text[pos]
            if char=='#':
                end=text.find('\n',pos);pos=len(text) if end<0 else end;continue
            if char=='{':depth+=1
            elif char=='}':depth-=1
            pos+=1
        section=text[block.end():pos-1]
        if re.search(r'\bserver_name\s+qa\.ltli\.ai\s*;',section) and re.search(r'\blisten\s+[^;]*\bssl\b',section):
            if re.search(r'\bauth_basic(?:_user_file)?\b',section):
                if ('auth_basic "LTLI Translate Development";' in section
                    and 'auth_basic_user_file /etc/nginx/.htpasswd-ltli-translate;' in section
                    and not re.search(r'auth_basic\s+off\s*;',section)):
                    continue
                raise ValueError('Existing authentication directives require manual review')
            matches.append(block.end())
    if len(matches)>1:raise ValueError('Multiple HTTPS QA blocks require review')
    if not matches:
        if 'auth_basic_user_file /etc/nginx/.htpasswd-ltli-translate;' in text:return text
        raise ValueError('No unique qa.ltli.ai HTTPS server found')
    pos=matches[0]
    return text[:pos]+'\n    auth_basic "LTLI Translate Development";\n    auth_basic_user_file /etc/nginx/.htpasswd-ltli-translate;\n'+text[pos:]

if __name__=='__main__':
    if os.geteuid()!=0:sys.exit('Run with sudo')
    target=pathlib.Path('/etc/nginx/sites-enabled/ltli-qa-public').resolve(strict=True)
    if not pathlib.Path('/etc/nginx/.htpasswd-ltli-translate').is_file():sys.exit('Translate password file is missing')
    original=target.read_text();changed=protect(original)
    if changed==original:sys.exit('QA authentication already configured; no changes')
    backup=pathlib.Path('/var/backups/ltli-nginx');backup.mkdir(parents=True,exist_ok=True)
    (backup/('qa-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')+'.conf')).write_text(original)
    target.write_text(changed)
    try:
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
    except subprocess.CalledProcessError:
        target.write_text(original)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise
    print('QA administrator authentication enabled')
