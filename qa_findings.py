"""Inspectable warning spans and reversible, content-bound human decisions."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import re
from qa_engine import (extract_numbers,extract_units,extract_tags,extract_placeholders,extract_urls,
                       extract_emails,extract_file_names,extract_shortcuts,extract_brackets)

EXTRACTORS={'Number mismatch':extract_numbers,'Unit mismatch':extract_units,'Tag mismatch':extract_tags,
 'Placeholder mismatch':extract_placeholders,'URL mismatch':extract_urls,'Email mismatch':extract_emails,
 'File name mismatch':extract_file_names,'Shortcut mismatch':extract_shortcuts,'Bracket mismatch':extract_brackets}
class ReviewError(ValueError):pass

def fingerprint(row):
    return hashlib.sha256(json.dumps([row['id'],row['source'],row['target']],ensure_ascii=False).encode()).hexdigest()

def token_spans(text,kind):
    if kind=='Number mismatch':return [(m.group(),m.start(),m.end()) for m in re.finditer(r'\d+(?:,\d{3})*(?:\.\d+)?',text)]
    if kind=='Tag mismatch':return [(m.group(),m.start(),m.end()) for m in re.finditer(r'</?[A-Za-z][^>]*?>',text)]
    values=EXTRACTORS[kind](text);found=[];offsets={}
    for value in values:
        if not value:continue
        if kind=='Shortcut mismatch':
            pattern=r'\s*'.join(re.escape(c) for c in value)
            match=re.search(pattern,text[offsets.get(value,0):],re.I)
            if not match:continue
            start=offsets.get(value,0)+match.start();end=offsets.get(value,0)+match.end()
        else:
            start=text.find(value,offsets.get(value,0));end=start+len(value)
            if start<0:continue
        offsets[value]=end;found.append((value,start,end))
    return found

def unmatched_spans(items,other):
    remaining=Counter(value for value,_,_ in other);spans=[]
    for value,start,end in items:
        if remaining[value]:remaining[value]-=1
        else:spans.append((start,end))
    return spans

def utf16(text,spans):
    # Browser String.slice uses UTF-16 offsets, not Python code-point indices.
    wanted={i for span in spans for i in span};offsets={};offset=0
    for index,char in enumerate(text):
        if index in wanted:offsets[index]=offset
        offset += 2 if ord(char)>0xffff else 1
    offsets[len(text)]=offset
    return [[offsets[a],offsets[b]] for a,b in spans if a<b]

def finding(row,issue):
    source,target=row['source'],row['target'];kind=issue.split(':',1)[0];a=[];b=[]
    if kind in EXTRACTORS:
        left,right=token_spans(source,kind),token_spans(target,kind)
        a,b=unmatched_spans(left,right),unmatched_spans(right,left)
    elif kind=='Punctuation mismatch':
        for text,out in ((source,a),(target,b)):
            match=re.search(r'[.!?:;]+(?=\s*$)',text)
            if match:out.append(match.span())
    elif kind=='Whitespace warning':
        b=[m.span() for m in re.finditer(r'^ +| +$| {2,}|\t',target)]
    elif kind=='Unbalanced target brackets':
        stack=[];pairs={')':'(',']':'[','}':'{'}
        for index,char in enumerate(target):
            if char in '([{':stack.append((char,index))
            elif char in pairs:
                if stack and stack[-1][0]==pairs[char]:stack.pop()
                else:b.append((index,index+1))
        b += [(i,i+1) for _,i in stack]
    elif kind in ('Missing translation','Source and target are identical'):
        a=[(0,len(source))];b=[(0,len(target))]
    return {'issue':issue,'source_spans':utf16(source,a),'target_spans':utf16(target,b)}

def annotate(result,decisions=None):
    decisions=[] if decisions is None else decisions
    if not isinstance(decisions,list) or len(decisions)>10000:raise ReviewError('review_request')
    valid=[];seen=set();lookup={r['id']:r for r in result['rows']}
    # all_issues includes out-of-scope rules, retaining judgments across filtered rechecks.
    for decision in decisions:
        if (not isinstance(decision,dict) or set(decision)!={'id','issue','fingerprint','accepted_at'}
            or type(decision['id']) is not int or not isinstance(decision['issue'],str)
            or not isinstance(decision['fingerprint'],str) or not isinstance(decision['accepted_at'],str)
            or len(decision['accepted_at'])>40):raise ReviewError('review_request')
        try:datetime.fromisoformat(decision['accepted_at'])
        except ValueError:raise ReviewError('review_request') from None
        row=lookup.get(decision['id']);key=(decision['id'],decision['issue'])
        if row and decision['fingerprint']==fingerprint(row) and decision['issue'] in row.get('all_issues',row['issues']) and key not in seen:
            seen.add(key);valid.append(dict(decision))
    for row in result['rows']:
        row['fingerprint']=fingerprint(row)
        row['accepted_issues']=[i for i in row['issues'] if (row['id'],i) in seen]
        row['active_issues']=[i for i in row['issues'] if (row['id'],i) not in seen]
        row['findings']=[finding(row,i) for i in row['issues']]
        row.pop('all_issues',None)
    result['detected_flagged']=sum(bool(r['issues']) for r in result['rows'])
    result['flagged']=sum(bool(r['active_issues']) for r in result['rows'])
    result['accepted_count']=sum(len(r['accepted_issues']) for r in result['rows'])
    result['decisions']=valid
    return result

def review(result,payload):
    if payload.get('operation') not in ('accept','restore') or type(payload.get('row_id')) is not int or not isinstance(payload.get('issue'),str):
        raise ReviewError('review_request')
    row=next((r for r in result['rows'] if r['id']==payload['row_id']),None)
    if not row or payload.get('fingerprint')!=row['fingerprint'] or payload['issue'] not in row['issues']:
        raise ReviewError('stale_review')
    decisions=[d for d in result['decisions'] if not(d['id']==row['id'] and d['issue']==payload['issue'])]
    if payload['operation']=='accept':
        decisions.append({'id':row['id'],'issue':payload['issue'],'fingerprint':row['fingerprint'],
                          'accepted_at':datetime.now(timezone.utc).isoformat()})
    # Re-annotation requires full rule results, supplied by the caller when rechecking.
    result=annotate(result,decisions)
    result['review_action']=payload['operation']
    return result
