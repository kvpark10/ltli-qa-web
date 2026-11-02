"""Best-effort admin completion notifications; never include document/user content."""
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
import logging
import os
import queue
import smtplib
import ssl
import threading

RECIPIENT='kvpark10@naver.com'
_EVENTS=queue.Queue(maxsize=100)
_LOCK=threading.Lock()
_WORKER=None
LOGGER=logging.getLogger(__name__)

def _address(value):
    if not value or '\r' in value or '\n' in value or parseaddr(value)[1]!=value or '@' not in value:
        raise ValueError('mail_address')
    return value

def build_message(event, sender):
    message=EmailMessage()
    message['From']=_address(sender)
    message['To']=RECIPIENT
    message['Subject']='[LTLI QA] 무료 QA 검사 완료'
    message['Date']=format_datetime(datetime.now(timezone.utc))
    message.set_content(
        '무료 QA 검사가 정상 완료되었습니다.\n\n'
        f"완료 시각 (UTC): {event['completed_at']}\n"
        f"검사 구간 수: {event['segments']}\n"
        f"QA 경고 수: {event['warnings']}\n"
        f"처리시간: {event['elapsed_ms']} ms\n\n"
        '원문·번역문·파일명·사용자 식별정보는 포함하지 않습니다.\n')
    return message

def _send(event):
    host=os.environ.get('LTLI_QA_SMTP_HOST','')
    user=os.environ.get('LTLI_QA_SMTP_USER','')
    password=os.environ.get('LTLI_QA_SMTP_PASSWORD','')
    sender=os.environ.get('LTLI_QA_SMTP_FROM',user)
    port=int(os.environ.get('LTLI_QA_SMTP_PORT','587'))
    if not host or not user or not password or not 1<=port<=65535:
        raise ValueError('smtp_config')
    message=build_message(event,sender)
    context=ssl.create_default_context()
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=10,context=context) as smtp:
            smtp.login(user,password)
            smtp.send_message(message,from_addr=sender,to_addrs=[RECIPIENT])
    else:
        with smtplib.SMTP(host,port,timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(user,password)
            smtp.send_message(message,from_addr=sender,to_addrs=[RECIPIENT])

def _consume():
    while True:
        event=_EVENTS.get()
        try:_send(event)
        except Exception:LOGGER.warning('QA completion email failed; no automatic retry')
        finally:_EVENTS.task_done()

def notify_qa(elapsed_ms, *, segments=None, warnings=None):
    if os.environ.get('LTLI_QA_EMAIL_ENABLED')!='1':return
    try:
        if any(type(x) is not int or x<0 for x in (elapsed_ms,segments,warnings)):return
        event={'completed_at':datetime.now(timezone.utc).isoformat(),
               'elapsed_ms':elapsed_ms,'segments':segments,'warnings':warnings}
        global _WORKER
        with _LOCK:
            if _WORKER is None or not _WORKER.is_alive():
                _WORKER=threading.Thread(target=_consume,daemon=True)
                _WORKER.start()
        _EVENTS.put_nowait(event)
    except queue.Full:LOGGER.warning('QA completion email queue full; event dropped')
    except Exception:LOGGER.warning('QA completion email unavailable')
