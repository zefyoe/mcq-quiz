"""Exercise anonymous booking, reservation contention and private data isolation."""
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)
os.environ.update(DATABASE_URL=f'sqlite:///{path}', SECRET_KEY='agenda-test', PUBLIC_SITE_MODE='active')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, db, appointment_slot_is_open
from models import Appointment, AppointmentHold, User

app.config['TESTING'] = True
try:
    with app.app_context():
        db.create_all()
        admin = User(email='y@bymed.be', is_admin=True)
        admin.set_password('test-password')
        db.session.add(admin)
        db.session.commit()
    first, second = app.test_client(), app.test_client()
    target = (datetime.now() + timedelta(days=7)).replace(hour=18, minute=20, second=0, microsecond=0)
    target += timedelta(days=(1-target.weekday()) % 7)
    day = target.date().isoformat()
    def token(client):
        page = client.get('/agenda?date=' + day)
        assert page.status_code == 200
        assert b'<html lang="fr">' in page.data
        assert b'href="/admin' not in page.data and b'href="/login' not in page.data
        return re.search(rb'name="csrf_token" value="([^"]+)"', page.data)[1].decode()
    t1, t2 = token(first), token(second)
    assert first.post('/agenda/hold', data={'slot_start': target.isoformat()}).status_code == 400
    assert first.post('/agenda/hold', data={'slot_start': target.isoformat(), 'csrf_token':t1}).status_code == 200
    assert second.post('/agenda/hold', data={'slot_start': target.isoformat(), 'csrf_token':t2}).status_code == 409
    held = second.get('/agenda?date=' + day).data
    assert ('data-slot="' + target.isoformat(timespec='minutes') + '"').encode() not in held
    data = dict(csrf_token=t1, slot_start=target.isoformat(), patient_name='SECRET PATIENT',
                patient_email='private@example.com', referring_doctor='SECRET DOCTOR',
                insurance_status='bim', inami_code='459712', notes='SECRET NOTES')
    assert first.post('/agenda/book', data=data).status_code == 200
    data['csrf_token'] = t2
    assert second.post('/agenda/book', data=data).status_code == 409
    with app.app_context():
        appointment = Appointment.query.one()
        assert appointment.duration_minutes == 10
        assert appointment.insurance_status == 'bim'
        assert appointment.prescription_data is None
        aid = appointment.id
    for client in (first, second):
        page = client.get('/agenda?date=' + day)
        for secret in (b'SECRET PATIENT', b'private@example.com', b'SECRET DOCTOR', b'SECRET NOTES'):
            assert secret not in page.data
        assert page.headers['Cache-Control'] == 'private, no-store'
        for route in ('/admin', '/admin/appointments', f'/admin/appointments/{aid}/prescription'):
            assert client.get(route).status_code == 302
        assert client.post(f'/admin/appointments/{aid}/cancel').status_code == 302
    first.post('/login', data={'email':'y@bymed.be', 'password':'test-password'})
    page = first.get('/admin/appointments?date=' + day)
    assert page.status_code == 200
    for value in (b'SECRET PATIENT', b'SECRET DOCTOR', b'BIM (VIPO)', b'Votre journ'):
        assert value in page.data
    assert b'SECRET PATIENT' not in first.get('/agenda?date=' + day).data
    # Expired reservation becomes claimable, and legacy 15-minute visits block overlapping slots.
    with app.app_context():
        db.session.add(Appointment(starts_at=target.replace(hour=19, minute=15), duration_minutes=15,
            patient_name='LEGACY', patient_email='legacy@example.com', appointment_type='Legacy'))
        db.session.add(AppointmentHold(starts_at=target.replace(hour=19, minute=40), token='old',
            expires_at=datetime.utcnow()-timedelta(minutes=1)))
        db.session.commit()
    assert second.post('/agenda/hold', data={'csrf_token':t2, 'slot_start':target.replace(hour=19, minute=20).isoformat()}).status_code == 409
    assert second.post('/agenda/hold', data={'csrf_token':t2, 'slot_start':target.replace(hour=19, minute=40).isoformat()}).status_code == 200
    # Boundaries: Tuesday/Thursday end at 20:10 and Saturday ends at 13:00.
    monday = datetime(2031, 1, 6)
    for weekday, hour, minute, expected in [(0,18,10,False),(1,18,0,False),(1,18,10,True),
        (1,20,0,True),(1,20,10,False),(2,18,10,False),(3,18,10,True),(4,18,10,False),
        (5,9,50,False),(5,10,0,True),(5,12,50,True),(5,13,0,False),(6,10,0,False)]:
        assert appointment_slot_is_open((monday+timedelta(days=weekday)).replace(hour=hour,minute=minute)) == expected
    assert second.post('/agenda/hold', data={'csrf_token':t2, 'slot_start':target.replace(hour=17).isoformat()}).status_code == 400
    assert second.post('/agenda/hold', data={'csrf_token':t2, 'slot_start':'2020-01-01T08:00'}).status_code == 400
    assert first.get('/admin/appointments?date=invalid').status_code == 200
    # Two independent browser sessions submit the same available slot together.
    third, fourth = app.test_client(), app.test_client()
    tokens = [token(third), token(fourth)]
    barrier = Barrier(2)
    def competing_booking(args):
        client, csrf = args
        payload = dict(data, csrf_token=csrf, slot_start=target.replace(minute=40).isoformat())
        barrier.wait()
        return client.post('/agenda/book', data=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(competing_booking, zip((third,fourth), tokens)))
    assert sorted(statuses) == [200,409], statuses
    print('Public agenda privacy, booking, holds and internal shift overview passed.')
finally:
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    os.unlink(path)
