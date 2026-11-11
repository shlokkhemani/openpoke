# Case set v2 — history review (Task 16)

Each changed case: the v1 history (off-product lines marked) and the v2 history (new turns marked), plus the context agent(s) added. Messages, labels and paraphrases are unchanged. Every new agent turn is preceded by a user line.

38 changed cases. Freeze after review: `python -m evals.run freeze-cases --dir evals/cases/v2`


## amb-person-001 (ambiguous_person)

Message: Can you email Alice and ask if she's free for an offsite planning call on Thursday?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Did any of my reminders go off?  ← new
- agent [ag_tvsjosvs]: Reminder: review open pull requests.  ← new
- assistant: Reminder: review open pull requests.  ← new

**Context agents added**

- `ag_tvsjosvs` Review PRs reminder (contacts: —) — Reminds the user every day at 8am to review open pull requests. The pull request is PR-3543.

## amb-person-003 (ambiguous_person)

Message: Can you email Alice and ask if she's free for an offsite planning call on Thursday?

**v1 history**

- user: Did Alice Chen approve the Q3 budget yet?
- assistant: Not yet. She asked for the vendor breakdown, which was sent on Tuesday. Still waiting on her sign-off.
- user: Thanks. Also, what's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Did Alice Chen approve the Q3 budget yet?
- assistant: Not yet. She asked for the vendor breakdown, which was sent on Tuesday. Still waiting on her sign-off.
- user: Did anything come in overnight?  ← new
- agent [ag_ajpksisi]: Here's your recruiting summary: 6 new items, nothing that needs an answer today.  ← new
- assistant: Here's your recruiting summary: 6 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_ajpksisi` Weekly recruiting summary (contacts: —) — Every monday at 8am, summarises the recruiting email threads and sends the summary to the user. The most recent one is DGT-68717.

## amb-person-005 (ambiguous_person)

Message: Email her and ask if she's free for an offsite planning call Thursday

**v1 history**

- user: Did Alice Chen approve the Q3 budget yet?
- assistant: Not yet. She asked for the vendor breakdown, which was sent on Tuesday. Still waiting on her sign-off.
- user: Thanks. Also, what's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Did Alice Chen approve the Q3 budget yet?
- assistant: Not yet. She asked for the vendor breakdown, which was sent on Tuesday. Still waiting on her sign-off.
- user: Did anything come in overnight?  ← new
- agent [ag_5awxogls]: Here's your calendar summary: 6 new items, nothing that needs an answer today.  ← new
- assistant: Here's your calendar summary: 6 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_5awxogls` Weekly calendar summary (contacts: —) — Every sunday at 7pm, summarises the upcoming calendar events and sends the summary to the user. The latest digest is DGT-37671.

## amb-person-006 (ambiguous_person)

Message: Has Daniel gotten back to you yet?

**v1 history**

- user: How long is the flight from Vancouver to Toronto?  ← off-product
- assistant: About four and a half hours, nonstop.

**v2 history**

- user: Did any of my reminders go off?  ← new
- agent [ag_jrt3ym3y]: Reminder: read for twenty minutes.  ← new
- assistant: Reminder: read for twenty minutes.  ← new

**Context agents added**

- `ag_jrt3ym3y` Read reminder (contacts: —) — Reminds the user every day at 9pm to read for twenty minutes. The reminder id is RMD-81808.

## amb-person-007 (ambiguous_person)

Message: Let her know I appreciate it, I've got things from here.

**v1 history**

- user: Do I have anything on Friday afternoon?  ← off-product
- assistant: Nothing scheduled. Your calendar is clear after 1pm.
- agent [ag_dcl3r2h4]: Update on the job offer paperwork: Farah replied that it arrived and looks fine.
- assistant: Farah Kowalski got back to you on that: Farah replied that it arrived and looks fine.

**v2 history**

- user: Did any of my reminders go off?  ← new
- agent [ag_zcnht4xa]: Reminder: review open pull requests.  ← new
- assistant: Reminder: review open pull requests.  ← new
- agent [ag_dcl3r2h4]: Update on the job offer paperwork: Farah replied that it arrived and looks fine.
- assistant: Farah Kowalski got back to you on that: Farah replied that it arrived and looks fine.

**Context agents added**

- `ag_zcnht4xa` Review PRs reminder (contacts: —) — Reminds the user every day at 12pm to review open pull requests. The pull request is PR-7596.

## broad-person-001 (broad_question_person)

Message: What's going on with Dana?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Any updates I should know about?  ← new
- agent [ag_72oxneof]: Here's your shipping summary: 3 new items, nothing that needs an answer today.  ← new
- assistant: Here's your shipping summary: 3 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_72oxneof` Nightly shipping summary (contacts: —) — Every day at 9pm, summarises the package and shipping updates and sends the summary to the user. Order ORD-46609 covers it.

## broad-person-002 (broad_question_person)

Message: Is there anything still open with Tomas Gallagher?

**v1 history**

- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Lena Quintero on getting the deposit back?  ← new
- agent [ag_dyqa7hai]: Update on getting the deposit back: Lena replied that the refund was processed.  ← new
- assistant: Lena replied that the refund was processed.  ← new

**Context agents added**

- `ag_dyqa7hai` Email Lena about deposit refund (contacts: Lena Quintero) — Emailed Lena Quintero about the security deposit refund. Lena replied that the refund was processed. Reference number REF-60893 is on file.

## broad-person-003 (broad_question_person)

Message: Any updates on the Liam stuff?

**v1 history**

- user: How long is the flight from Vancouver to Toronto?  ← off-product
- assistant: About four and a half hours, nonstop.
- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Fiona Lindqvist on the deadline extension?  ← new
- agent [ag_7itnrndm]: Update on the deadline extension: Fiona replied that the new date works.  ← new
- assistant: Fiona replied that the new date works.  ← new
- user: Anything new in my inbox?  ← new
- agent [ag_w6proags]: Here's your support ticket summary: 5 new items, nothing that needs an answer today.  ← new
- assistant: Here's your support ticket summary: 5 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_7itnrndm` Follow up with Fiona on project deadline (contacts: Fiona Lindqvist, Sana Weber) — Emailed Fiona Lindqvist about moving the project deadline by a week. Fiona replied that the new date works. The thread is saved as MSG-12847.
- `ag_w6proags` Monthly support ticket summary (contacts: —) — On the 1st of every month at 9am, summarises the support ticket emails and sends the summary to the user. Support case #Q-14068 tracks it.

## broad-person-004 (broad_question_person)

Message: Quick check: what's the latest on Isaac Brennan?

**v1 history**

- user: Convert 20 miles to kilometres.  ← off-product
- assistant: 20 miles is about 32 kilometres.
- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: What's on my plate today?  ← new
- agent [ag_hn3twdnz]: Reminder: book a dinner for the anniversary.  ← new
- assistant: Reminder: book a dinner for the anniversary.  ← new
- user: Did any of my reminders go off?  ← new
- agent [ag_2sb7la67]: Reminder: renew the domain name.  ← new
- assistant: Reminder: renew the domain name.  ← new

**Context agents added**

- `ag_hn3twdnz` Anniversary reminder (contacts: —) — Reminds the user every year on March 3 to book a dinner for the anniversary. Confirmation CONF-5ZEXIM was issued.
- `ag_2sb7la67` Domain renewal reminder (contacts: —) — Reminds the user on the 1st of every month at 9am to renew the domain name. Reference number REF-79773 is on file.

## broad-person-006 (broad_question_person)

Message: Is there anything still open with Helena Rossi?

**v1 history**

- user: Do I have anything on Friday afternoon?  ← off-product
- assistant: Nothing scheduled. Your calendar is clear after 1pm.

**v2 history**

- user: Any updates I should know about?  ← new
- agent [ag_7rwmrgrt]: Here's your shipping summary: 4 new items, nothing that needs an answer today.  ← new
- assistant: Here's your shipping summary: 4 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_7rwmrgrt` Weekday shipping summary (contacts: —) — Every weekday at 8am, summarises the package and shipping updates and sends the summary to the user. Order ORD-24294 covers it.

## clear-person-001 (clear_person)

Message: Can you email Alice Chen and ask if she's free for an offsite planning call on Thursday?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Any news from Zane Tanaka on the paperwork for taxes?  ← new
- agent [ag_oho5z2l5]: Update on the paperwork for taxes: Zane replied that the accountant has what is needed.  ← new
- assistant: Zane replied that the accountant has what is needed.  ← new

**Context agents added**

- `ag_oho5z2l5` Follow up with Zane on tax documents (contacts: Zane Tanaka) — Emailed Zane Tanaka about the tax documents for last year. Zane replied that the accountant has what is needed. Reference number REF-26031 is on file.

## clear-person-002 (clear_person)

Message: Can you shoot Sam Rivera a quick text and see if I can borrow a drill this weekend?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Anything I need to do today?  ← new
- agent [ag_3j47yivk]: Reminder: take your vitamins.  ← new
- assistant: Reminder: take your vitamins.  ← new

**Context agents added**

- `ag_3j47yivk` Vitamins reminder (contacts: —) — Reminds the user every Monday at 8am to take their vitamins. The prescription number is RX-154221.

## clear-person-003 (clear_person)

Message: Could you drop Elena Zielinski a note and ask if she'd suggest a few books I should pick up?

**v1 history**

- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.
- user: What did Elena Sandoval say about the school conference time?
- assistant: Elena replied that Thursday afternoon works. Nothing else is needed from you right now.

**v2 history**

- user: What's on my plate today?  ← new
- agent [ag_ft33ftgo]: Reminder: clear the inbox.  ← new
- assistant: Reminder: clear the inbox.  ← new
- user: What did Elena Sandoval say about the school conference time?
- assistant: Elena replied that Thursday afternoon works. Nothing else is needed from you right now.

**Context agents added**

- `ag_ft33ftgo` Inbox zero reminder (contacts: —) — Reminds the user every day at 12pm to clear the inbox. The reminder id is RMD-16194.

## clear-person-004 (clear_person)

Message: Could you shoot Priya Raman a text and find out when they're next coming to town?

**v1 history**

- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Gabriel Eriksen on lending me the packing boxes?  ← new
- agent [ag_w3t6uzbi]: Update on lending me the packing boxes: Gabriel replied that they can drop them off on Saturday.  ← new
- assistant: Gabriel replied that they can drop them off on Saturday.  ← new

**Context agents added**

- `ag_w3t6uzbi` Email Gabriel re moving boxes (contacts: Gabriel Eriksen) — Emailed Gabriel Eriksen about borrowing the moving boxes. Gabriel replied that they can drop them off on Saturday. The thread is saved as MSG-56654.

## clear-person-005 (clear_person)

Message: Did Farah Moreau mention anything about the interview write-up?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Did any of my reminders go off?  ← new
- agent [ag_m4l43mia]: Reminder: review open pull requests.  ← new
- assistant: Reminder: review open pull requests.  ← new

**Context agents added**

- `ag_m4l43mia` Review PRs reminder (contacts: —) — Reminds the user every day at 12pm to review open pull requests. The pull request is PR-4568.

## clear-person-006 (clear_person)

Message: Email Daniel Walsh and ask if they're coming to the barbecue on Saturday.

**v1 history**

- user: Do I have anything on Friday afternoon?  ← off-product
- assistant: Nothing scheduled. Your calendar is clear after 1pm.

**v2 history**

- user: Any news from Ruth Zhang on the new hire's setup list?  ← new
- agent [ag_2qo7jbyv]: Update on the new hire's setup list: Ruth replied that the laptop ships Monday.  ← new
- assistant: Ruth replied that the laptop ships Monday.  ← new

**Context agents added**

- `ag_2qo7jbyv` Follow up with Ruth on onboarding checklist (contacts: Ruth Zhang) — Emailed Ruth Zhang about the onboarding checklist for the new hire. Ruth replied that the laptop ships Monday. Order ORD-94826 covers it.

## followup-001 (email_followup)

Message: Any update from the landlord on the kitchen repair?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Anything I need to do today?  ← new
- agent [ag_orcr36a4]: Reminder: do the daily Spanish lesson.  ← new
- assistant: Reminder: do the daily Spanish lesson.  ← new

**Context agents added**

- `ag_orcr36a4` Language practice reminder (contacts: —) — Reminds the user every day at 9pm to do the daily Spanish lesson. It is saved as reminder RMD-59546.

## followup-002 (email_followup)

Message: Look again for messages from Priya regarding the annual tax filing.

**v1 history**

- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.

**v2 history**

- user: Any news from Fiona Zhang on pushing the due date back a week?  ← new
- agent [ag_5camm5ov]: Update on pushing the due date back a week: Fiona replied that the new date works.  ← new
- assistant: Fiona replied that the new date works.  ← new

**Context agents added**

- `ag_5camm5ov` Email Fiona about project deadline (contacts: Fiona Zhang) — Emailed Fiona Zhang about moving the project deadline by a week. Fiona replied that the new date works. The thread is saved as MSG-57966.

## followup-003 (email_followup)

Message: Did Carmen Brennan mention anything about the new higher price?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.
- user: Thanks, that's all for now.
- assistant: You're welcome. I'm here if anything comes up.

**v2 history**

- user: Anything new in my inbox?  ← new
- agent [ag_65mdheqo]: Here's your school summary: 7 new items, nothing that needs an answer today.  ← new
- assistant: Here's your school summary: 7 new items, nothing that needs an answer today.  ← new
- user: Thanks, that's all for now.
- assistant: You're welcome. I'm here if anything comes up.

**Context agents added**

- `ag_65mdheqo` Weekday school summary (contacts: —) — Every weekday at 6pm, summarises the emails from the kids' school and sends the summary to the user. The latest digest is DGT-29455.

## followup-004 (email_followup)

Message: Haven't heard back from Quinn Nakamura about the security review findings, can you follow up with them?

**v1 history**

- user: Convert 20 miles to kilometres.  ← off-product
- assistant: 20 miles is about 32 kilometres.
- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Anything I need to do today?  ← new
- agent [ag_vwf5arsr]: Reminder: take the evening medication.  ← new
- assistant: Reminder: take the evening medication.  ← new
- user: Anything new in my inbox?  ← new
- agent [ag_42wz3cre]: Here's your calendar summary: 5 new items, nothing that needs an answer today.  ← new
- assistant: Here's your calendar summary: 5 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_vwf5arsr` Medication reminder (contacts: —) — Reminds the user every Monday at 8am to take the evening medication. Prescription RX-273812 is on file.
- `ag_42wz3cre` Weekday calendar summary (contacts: —) — Every weekday at 8am, summarises the upcoming calendar events and sends the summary to the user. The latest digest is DGT-72678.

## followup-005 (email_followup)

Message: Could you look through my email again for any new messages from Amara about the party plans?

**v1 history**

- user: How long is the flight from Vancouver to Toronto?  ← off-product
- assistant: About four and a half hours, nonstop.
- user: Thanks, that's all for now.
- assistant: You're welcome. I'm here if anything comes up.

**v2 history**

- user: Any updates I should know about?  ← new
- agent [ag_upxeow5g]: Here's your receipt summary: 7 new items, nothing that needs an answer today.  ← new
- assistant: Here's your receipt summary: 7 new items, nothing that needs an answer today.  ← new
- user: Thanks, that's all for now.
- assistant: You're welcome. I'm here if anything comes up.

**Context agents added**

- `ag_upxeow5g` Weekly receipt summary (contacts: —) — Every sunday at 7pm, summarises the purchase receipts and sends the summary to the user. Order ORD-33766 covers it.

## followup-006 (email_followup)

Message: Did Theo ever reply about the deadline extension? Can you look?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Any updates I should know about?  ← new
- agent [ag_mtagzkm7]: Here's your expense summary: 2 new items, nothing that needs an answer today.  ← new
- assistant: Here's your expense summary: 2 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_mtagzkm7` Weekday expense summary (contacts: —) — Every weekday at 6pm, summarises the card and receipt emails and sends the summary to the user. It is filed under reference REF-21069.

## multi-intent-002 (multi_intent)

Message: Let Omar Underwood know I'll be home Saturday morning for the new monitor delivery, and set a reminder for 9:30am that day to clear my desk.

**v1 history**

- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Anything new in my inbox?  ← new
- agent [ag_e6zme236]: Here's your receipt summary: 7 new items, nothing that needs an answer today.  ← new
- assistant: Here's your receipt summary: 7 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_e6zme236` Weekday receipt summary (contacts: —) — Every weekday at 6pm, summarises the purchase receipts and sends the summary to the user. The order number is ORD-10406.

## multi-intent-003 (multi_intent)

Message: Can you shoot Wendy Lindqvist an email asking if she'd water my plants while I'm out next week? Also, push the garbage bins reminder back to 7pm.

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.
- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Zane Torres on extending the freelance agreement?  ← new
- agent [ag_dgikgrv6]: Update on extending the freelance agreement: Zane replied that the renewal terms are attached.  ← new
- assistant: Zane replied that the renewal terms are attached.  ← new
- user: What's on my plate today?  ← new
- agent [ag_25isscvz]: Reminder: update the roadmap doc.  ← new
- assistant: Reminder: update the roadmap doc.  ← new

**Context agents added**

- `ag_dgikgrv6` Follow up with Zane on contract renewal (contacts: Zane Torres) — Emailed Zane Torres about renewing the freelance contract. Zane replied that the renewal terms are attached. It is filed under reference REF-74382.
- `ag_25isscvz` Update roadmap reminder (contacts: —) — Reminds the user every day at 8am to update the roadmap doc. It is saved as reminder RMD-50385.

## multi-intent-004 (multi_intent)

Message: Tell Rafael Yilmaz that Tuesday at 3pm is fine for the dentist, and push the dentist booking reminder back to 6pm.

**v1 history**

- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.

**v2 history**

- user: Anything new in my inbox?  ← new
- agent [ag_42wz3cre]: Here's your calendar summary: 8 new items, nothing that needs an answer today.  ← new
- assistant: Here's your calendar summary: 8 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_42wz3cre` Weekday calendar summary (contacts: —) — Every weekday at 8am, summarises the upcoming calendar events and sends the summary to the user. The latest digest is DGT-72678.

## multi-intent-005 (multi_intent)

Message: Shoot Jamal Kowalski a note that Friday's team lunch has shifted to 1pm, and set a reminder for me at 12:30pm that day so I don't forget to book the table.

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Any news from Josefina Pereira on catering for the launch?  ← new
- agent [ag_zi77ifox]: Update on catering for the launch: Josefina replied that the menu is locked in.  ← new
- assistant: Josefina replied that the menu is locked in.  ← new

**Context agents added**

- `ag_zi77ifox` Follow up with Josefina on catering order (contacts: Josefina Pereira) — Emailed Josefina Pereira about the catering order for the launch party. Josefina replied that the menu is locked in. The order number is ORD-55374.

## multi-intent-006 (multi_intent)

Message: Shoot Greta Silva an email asking if I can borrow her bike pump this weekend, and also push my bike tune-up reminder back to 8pm.

**v1 history**

- user: What day is the first of next month?
- assistant: It falls on a Monday.
- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.

**v2 history**

- user: What day is the first of next month?
- assistant: It falls on a Monday.
- user: Any news from Helena Rossi on catering for the launch?  ← new
- agent [ag_m57q5oei]: Update on catering for the launch: Helena replied that the menu is locked in.  ← new
- assistant: Helena replied that the menu is locked in.  ← new

**Context agents added**

- `ag_m57q5oei` Follow up with Helena on catering order (contacts: Helena Rossi) — Emailed Helena Rossi about the catering order for the launch party. Helena replied that the menu is locked in. Order ORD-60966 covers it.

## multi-person-001 (multi_person)

Message: Hey, could you see if Aaron Castillo has gotten around to reading the pitch doc yet? Also, reach out to Theo Brennan and ask if he knows a decent plumber.

**v1 history**

- user: What day is the first of next month?
- assistant: It falls on a Monday.
- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.

**v2 history**

- user: What day is the first of next month?
- assistant: It falls on a Monday.
- user: Did any of my reminders go off?  ← new
- agent [ag_73nyuwxg]: Reminder: write notes for stand-up.  ← new
- assistant: Reminder: write notes for stand-up.  ← new

**Context agents added**

- `ag_73nyuwxg` Stand-up prep reminder (contacts: —) — Reminds the user every day at 9pm to write notes for stand-up. It is saved as reminder RMD-35616.

## multi-person-002 (multi_person)

Message: Can you check whether Colin Estrada and Carmen Brennan are open for lunch Thursday?

**v1 history**

- user: Do I have anything on Friday afternoon?  ← off-product
- assistant: Nothing scheduled. Your calendar is clear after 1pm.
- user: How long is the flight from Vancouver to Toronto?  ← off-product
- assistant: About four and a half hours, nonstop.

**v2 history**

- user: Any news from Sana Weber on the medical test results?  ← new
- agent [ag_avxydnpv]: Update on the medical test results: Sana replied that the results are available in the portal.  ← new
- assistant: Sana replied that the results are available in the portal.  ← new
- user: Any news from Tomas Gallagher on the car maintenance booking?  ← new
- agent [ag_t4622w3n]: Update on the car maintenance booking: Tomas replied that the slot is confirmed.  ← new
- assistant: Tomas replied that the slot is confirmed.  ← new

**Context agents added**

- `ag_avxydnpv` Email Sana re lab results (contacts: Sana Weber) — Emailed Sana Weber about the lab results appointment. Sana replied that the results are available in the portal. Reference number REF-82827 is on file.
- `ag_t4622w3n` Email Tomas about car service (contacts: Tomas Gallagher) — Emailed Tomas Gallagher about booking the car service. Tomas replied that the slot is confirmed. Confirmation CONF-F54YUP was issued.

## multi-person-003 (multi_person)

Message: Can you check whether Alice and Sam Rivera are free for coffee next week?

**v1 history**

- user: How long is the flight from Vancouver to Toronto?  ← off-product
- assistant: About four and a half hours, nonstop.
- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Did anything come in overnight?  ← new
- agent [ag_tsekgzdv]: Here's your receipt summary: 9 new items, nothing that needs an answer today.  ← new
- assistant: Here's your receipt summary: 9 new items, nothing that needs an answer today.  ← new
- user: Any news from Imani Brennan on the rate hike?  ← new
- agent [ag_6qcrp7gd]: Update on the rate hike: Imani replied that the old rate holds until January.  ← new
- assistant: Imani replied that the old rate holds until January.  ← new

**Context agents added**

- `ag_tsekgzdv` Nightly receipt summary (contacts: —) — Every day at 9pm, summarises the purchase receipts and sends the summary to the user. The order number is ORD-42801.
- `ag_6qcrp7gd` Follow up with Imani on price increase (contacts: Imani Brennan) — Emailed Imani Brennan about the announced price increase. Imani replied that the old rate holds until January. Reference number REF-52777 is on file.

## multi-person-004 (multi_person)

Message: Can you ping Paloma Zielinski about getting the new hire set up, and also see if Mateo Petrov has had a look at my revised CV yet?

**v1 history**

- user: Convert 20 miles to kilometres.  ← off-product
- assistant: 20 miles is about 32 kilometres.
- user: What's on my calendar tomorrow?  ← off-product
- assistant: A team lunch at noon and a one-on-one at 3:30.

**v2 history**

- user: Did anything come in overnight?  ← new
- agent [ag_y36jj43i]: Here's your support ticket summary: 2 new items, nothing that needs an answer today.  ← new
- assistant: Here's your support ticket summary: 2 new items, nothing that needs an answer today.  ← new
- user: Any news from Kemal Kowalski on the countersigned offer?  ← new
- agent [ag_iqbteomv]: Update on the countersigned offer: Kemal replied that it arrived and looks fine.  ← new
- assistant: Kemal replied that it arrived and looks fine.  ← new

**Context agents added**

- `ag_y36jj43i` Morning support ticket summary (contacts: —) — Every day at 7am, summarises the support ticket emails and sends the summary to the user. Support case #Q-48675 tracks it.
- `ag_iqbteomv` Email Kemal about offer letter (contacts: Kemal Kowalski) — Emailed Kemal Kowalski about the signed offer letter. Kemal replied that it arrived and looks fine. It is filed under reference REF-33773.

## multi-person-005 (multi_person)

Message: Check with Liam Bianchi if there's any update on the billing dispute, and send Amara Abara an email asking who her hairdresser is.

**v1 history**

- user: Convert 20 miles to kilometres.  ← off-product
- assistant: 20 miles is about 32 kilometres.
- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Ruth Zhang on getting the new employee set up?  ← new
- agent [ag_2qo7jbyv]: Update on getting the new employee set up: Ruth replied that the laptop ships Monday.  ← new
- assistant: Ruth replied that the laptop ships Monday.  ← new
- user: Any news from Lena Quintero on last year's tax forms?  ← new
- agent [ag_frroukm2]: Update on last year's tax forms: Lena replied that the accountant has what is needed.  ← new
- assistant: Lena replied that the accountant has what is needed.  ← new

**Context agents added**

- `ag_2qo7jbyv` Follow up with Ruth on onboarding checklist (contacts: Ruth Zhang) — Emailed Ruth Zhang about the onboarding checklist for the new hire. Ruth replied that the laptop ships Monday. Order ORD-94826 covers it.
- `ag_frroukm2` Follow up with Lena on tax documents (contacts: Lena Quintero) — Emailed Lena Quintero about the tax documents for last year. Lena replied that the accountant has what is needed. Reference number REF-48500 is on file.

## multi-person-006 (multi_person)

Message: Ask Sam and Alice Chen if they'd like to join the running club on Sundays.

**v1 history**

- user: Is it going to rain in Seattle tomorrow?  ← off-product
- assistant: Light rain in the morning, clearing by noon.

**v2 history**

- user: Any news from Noor Fitzgerald on getting the car serviced?  ← new
- agent [ag_qtqviwbs]: Update on getting the car serviced: Noor replied that the slot is confirmed.  ← new
- assistant: Noor replied that the slot is confirmed.  ← new

**Context agents added**

- `ag_qtqviwbs` Email Noor about car service (contacts: Noor Fitzgerald) — Emailed Noor Fitzgerald about booking the car service. Noor replied that the slot is confirmed. The confirmation code is CONF-DXZ7F7.

## newtask-001 (new_task_lookalike)

Message: Email my landlord and ask if I'm allowed to paint the bedroom.

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Did anything come in overnight?  ← new
- agent [ag_rpbud4dj]: Here's your school summary: 2 new items, nothing that needs an answer today.  ← new
- assistant: Here's your school summary: 2 new items, nothing that needs an answer today.  ← new

**Context agents added**

- `ag_rpbud4dj` Weekday school summary (contacts: —) — Every weekday at 8am, summarises the emails from the kids' school and sends the summary to the user. The most recent one is DGT-19891.

## newtask-002 (new_task_lookalike)

Message: I want a recap of my Figma comments every weekday at 8am.

**v1 history**

- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.

**v2 history**

- user: Any news from Priya Raman on the feedback on the design deck?  ← new
- agent [ag_bzxcbyn5]: Update on the feedback on the design deck: Priya replied that two slides need rework.  ← new
- assistant: Priya replied that two slides need rework.  ← new

**Context agents added**

- `ag_bzxcbyn5` Email Priya about design review (contacts: Priya Raman) — Emailed Priya Raman about feedback on the design review slides. Priya replied that two slides need rework. Thread MSG-82410 holds the full exchange.

## newtask-006 (new_task_lookalike)

Message: Could you put a daily 8am reminder on my calendar to back up the photos on my phone?

**v1 history**

- user: What's the weather like this weekend?  ← off-product
- assistant: Mostly sunny on Saturday, with showers likely on Sunday afternoon.
- user: What day is the first of next month?
- assistant: It falls on a Monday.

**v2 history**

- user: Any news from Nikhil Rossi on access to the shared account?  ← new
- agent [ag_uz7igbah]: Update on access to the shared account: Nikhil replied that access has been restored.  ← new
- assistant: Nikhil replied that access has been restored.  ← new
- user: What day is the first of next month?
- assistant: It falls on a Monday.

**Context agents added**

- `ag_uz7igbah` Email Nikhil re password reset (contacts: Nikhil Rossi) — Emailed Nikhil Rossi about the shared account password reset. Nikhil replied that access has been restored. Ticket #Q-17656 was opened for it.

## trigger-001 (trigger_management)

Message: Can you push my evening email recap to 8 instead?

**v1 history**

- user: What's on my calendar tomorrow?  ← off-product
- assistant: Two things: standup at 9:30 and a dentist appointment at 2pm.

**v2 history**

- user: Any news from Josefina Sandoval on the contract markup from the vendor?  ← new
- agent [ag_rolwliox]: Update on the contract markup from the vendor: Josefina replied that legal is still reviewing it.  ← new
- assistant: Josefina replied that legal is still reviewing it.  ← new

**Context agents added**

- `ag_rolwliox` Follow up with Josefina on vendor contract (contacts: Josefina Sandoval) — Emailed Josefina Sandoval about the vendor contract redlines. Josefina replied that legal is still reviewing it. Reference number REF-75757 is on file.

## trigger-005 (trigger_management)

Message: Could you shift the weekday 6pm trip bookings digest over to 6am instead?

**v1 history**

- user: Convert 20 miles to kilometres.  ← off-product
- assistant: 20 miles is about 32 kilometres.

**v2 history**

- user: Any news from Owen Sandoval on the offsite schedule?  ← new
- agent [ag_o7ne3kk4]: Update on the offsite schedule: Owen replied that the venue is confirmed.  ← new
- assistant: Owen replied that the venue is confirmed.  ← new

**Context agents added**

- `ag_o7ne3kk4` Email Owen about team offsite (contacts: Owen Sandoval) — Emailed Owen Sandoval about the agenda for the team offsite. Owen replied that the venue is confirmed. Confirmation CONF-CW22PA was issued.
