FitZone – Unified Odoo Solution (Release 1)

A custom Odoo 19 module that unifies FitZone's gym operations in one system.

About FitZone

Client: FitZone, a fitness center owned by Omar Marashdeh. Delivered by: Iron Coders (Hmmam Al-Sukhni, Doha Al-Omari, Noor Al-Rawashdeh). Scope baseline: FitZone Business Requirements Document (BRD) v1.0, 30 September 2026.

FitZone offers gym memberships, group classes, personal training, a swimming pool, physiotherapy and nutrition services, and a retail shop for supplements and health products.

The problem

Today most of this runs on paper sheets and Excel, and the services are disconnected from each other:

Membership, payments and freezes are tracked by hand, and expiry dates are adjusted manually.
Reception cannot check validity or remaining visits at the door.
Trainers can be double-booked, and class capacity is not enforced (the CrossFit room holds 15 but regularly gets 20 to 22 people).
Equipment faults and periodic maintenance dates are missed.
Injuries are recorded on paper with no path from the trainer to the clinic.
Supplement stock and expiry dates are not controlled.
The manager has no consolidated view of revenue, utilisation or injuries.
What this project delivers

One unified Odoo system with one record per member, visible to every department according to role. Release 1 covers 13 modules:

1.REG: Registration and Membership
2.VIS: Visit Tracking and Barcode Check-in
3.PAY: Payments, Instalments and Invoicing
4.RET: Retail and Member Discount
5.INV: Inventory
6.CLS: Group Classes and Trainer Scheduling
7.PT: Personal Training and Commission
8.POOL: Swimming Pool
9.HLT: Health and Nutrition Assessments
10.INJ: Injuries and Rehabilitation
11.STF: Staff Directory and Access
12.MNT: Equipment Maintenance
3.RPT: Management Reporting

Standard Odoo is used first (BRD NFR-07). Custom development covers REG, VIS, PAY, CLS, PT, POOL, HLT, INJ and MNT. RET, INV, STF and RPT are mainly configuration.

Out of scope for Release 1

Waiting list for full classes, instalments for memberships shorter than 3 months, refunds after a subscription starts, corporate memberships, late-payment fees, import of historical financial data, trainer attendance deductions, and stock tracking of juices and snacks.

Team : 
Hmmam Alsukhni	
Doha Alomari	
Nour AlRwashdeh
