prep.md

project name: Gpron Integrated Service Platform

project type: full stack web application with role based system

reference design:
[https://azim.hostlin.com/Watertown/price.html](https://azim.hostlin.com/Watertown/price.html)

design inspiration:
Modern gradient based UI inspired by AI mobile interface aesthetics. Clean, soft, minimal, with layered cards and subtle shadows.

color system:

primary gradient:
dark emerald: #0B3D2E
deep green: #0F5C4A
soft green: #1F8A70

secondary accents:
soft mint: #A8E6CF
light sage: #DFF5EC

neutral palette:
background: #F7F9F8
card background: #FFFFFF
border: #E6ECEA

text colors:
primary text: #1A1A1A
secondary text: #5F6F68
muted text: #8A9A94

ui behavior:
gradients must be used in hero sections, buttons, and key highlights
avoid flat blue tones entirely
soft shadows and rounded cards must be consistent across the system
transitions should feel smooth and modern

1. system purpose

Gpron Integrated Service is a digital platform designed to transform a traditional laundry and dry cleaning business into a structured, trackable, and scalable software driven system.

The platform enables customers to place and track orders while providing managers with full operational visibility and control.

2. core system architecture

architecture type:
monolithic backend with modular separation

system layers:

frontend:
customer web interface
manager dashboard interface

backend:
centralized api server
authentication service
order processing engine
tracking system

database:
single centralized database

3. role based system

roles:

customer:
register and login
place orders
select service type
track order status
receive updates

manager:
access all orders
update order lifecycle
manage customers
monitor operations

future roles:
delivery personnel
system administrator

access control:

strict role based access control enforced at api level
customers can only access their own records
managers have system wide visibility

4. system modules

4.1 authentication module
user registration
login system
password hashing
jwt based authentication
role assignment

4.2 order management module
create new order
assign unique tracking id
select service type express or normal
automatic pricing logic
store and update order data

4.3 tracking system
generate tracking id example GPRON-2026-0001
allow tracking via dashboard and public tracking page
show real time order progress

4.4 order lifecycle engine

order states:

pending
picked up
in cleaning
ready
delivered

only managers can modify state transitions

4.5 notification system
order confirmation alerts
status update notifications
delivery completion alerts

4.6 newsletter module
user email subscription
email storage and management

5. database design

users:
id
name
email
password_hash
role
created_at

orders:
id
user_id
tracking_id
service_type
status
price
created_at
updated_at

logs:
id
action
user_id
timestamp

newsletter:
id
email
subscribed_at

6. api design

authentication:
POST /register
POST /login

orders:
POST /orders
GET /orders/user
GET /orders/all
PATCH /orders/status

tracking:
GET /track/{tracking_id}

newsletter:
POST /subscribe

7. frontend structure

customer interface:
landing page with gradient hero section
service selection page
order placement form
tracking interface
user dashboard

manager dashboard:
all orders table view
filtering system based on status
order status update panel
customer overview
simple analytics view

ui rules:
all major sections must use gradient headers
cards must have rounded corners and soft shadows
spacing must feel breathable and modern

8. config system

environment variables stored in .env:

DATABASE_URL
SECRET_KEY
EMAIL_SERVICE_KEY

rules:
no hardcoded credentials
all sensitive values must be loaded from environment

9. security architecture

bcrypt password hashing
jwt authentication
input validation across all endpoints
rate limiting
role based access enforcement

10. privacy and compliance

data minimization:
only required user data is collected

secure handling:
sensitive data protected
no exposure of internal identifiers

environment rules:
.env must never be committed
.env must be included in .gitignore
.env.example must be provided

logging:
no sensitive data in logs

access control:
strict role enforcement at all endpoints

general compliance:
follow standard data protection principles
ensure user isolation across roles

11. software hygiene

linting:
ruff

formatting:
black

testing:
pytest

commands:
ruff check .
black .
pytest

ci:
lint and test must run on every push

12. development experience

hot reload:

backend:
uvicorn app.main:app --reload

frontend:
live reload enabled

rules:
no manual refresh required
changes must reflect instantly

13. cli behavior

start backend:
uvicorn app.main:app --reload

start frontend:
npm run dev

run tests:
pytest

14. storage and registry design

centralized database storage
tracking id used as public identifier
internal ids hidden from users

15. roadmap

v1:
order system
tracking system
manager dashboard

v2:
notifications
analytics dashboard
refined ui

v3:
delivery staff system
mobile version
intelligent demand prediction

16. definition of done

the system is complete when:

users can register and login
customers can place orders
tracking system works end to end
managers can update order status
database integration is complete
security and compliance rules are enforced
hot reload is functional
code passes linting and testing

