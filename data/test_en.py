from __future__ import annotations

TEST_CATEGORIES = [
    ("", "root"),
    ("root", "work"),
    ("root", "personal"),
    ("root", "learning"),
    ("root", "ideas"),
]

PREFERENCE_FRAGMENTS: list[tuple[str, str]] = [
    # --- root.work Work Related (64 items) ---
    ("root.work",
     "Core work hours are strictly limited to 9:00-18:00 to maintain a healthy work-life boundary. The 12:00-13:30 lunch break must be spent away from the desk, preferably taking a 15-minute walk downstairs to switch brain contexts."
     ),
    ("root.work",
     "The IDE (like VS Code/IntelliJ) and terminal must universally use dark, high-contrast themes (like One Dark Pro). This significantly reduces visual fatigue and photophobia caused by staring at screens for extended periods."
     ),
    ("root.work",
     "Before important cross-departmental or client meetings, I habitually set a strong 15-minute advance reminder on Feishu/DingTalk to check casting equipment and review core agenda items. I never enter a meeting room right on the dot."
     ),
    ("root.work",
     "No deep coding or complex architectural design is scheduled after 15:00 on Fridays. This low-coding-power period is specifically reserved for weekly retrospectives, updating my personal Wiki, and planning priorities for the following week."
     ),
    ("root.work",
     "When doing Code Reviews, I habitually filter out security-sensitive core links like authentication, encryption, and SQL concatenation first. Only after confirming there are no unauthorized access or injection risks do I review business logic and coding conventions."
     ),
    ("root.work",
     "Daily Agile Standups adhere to the 'discuss the issue, not the details' principle and are strictly kept under 15 minutes. Technical bottlenecks requiring deep discussion are deferred to small post-standup meetings with relevant personnel."
     ),
    ("root.work",
     "The first PR of any new project must be a comprehensive README.md, containing local setup instructions and an initial system interaction architecture diagram drawn with PlantUML/Mermaid."
     ),
    ("root.work",
     "The local development environment must have pre-commit hooks configured. Before every git commit, ESLint/Prettier and unit tests for core modules run automatically to block trivial syntax errors from entering the remote repository."
     ),
    ("root.work",
     "When working remotely from home, to avoid being distracted by chores, I prefer using the Pomodoro technique (25 minutes of focus + 5 minutes of stretching) accompanied by a physical desktop countdown clock to reinforce the ritual of focus."
     ),
    ("root.work",
     "Weekly report habit: Written in the last half-hour before clocking out on Friday. The fixed structure is 'Core deliverables (with links) + Blockers & required resource support + High-priority plans for next week'."
     ),
    ("root.work",
     "Tech stack selection values: When evaluating new frameworks, the team's learning curve and community activity are the top priorities. Only then do I consider whether it uses the absolute bleeding-edge underlying technology."
     ),
    ("root.work",
     "Updates to documentation (Swagger/Wiki) must be synchronously submitted in the exact same MR/PR as the code changes. I reject the 'code first, doc later' practice to prevent knowledge drift."
     ),
    ("root.work",
     "During product requirement reviews, my first reaction is always to ask the PM about business boundary conditions (e.g., maximum concurrent traffic estimates) and degradation strategies for extreme edge cases, rather than immediately thinking about implementation details."
     ),
    ("root.work",
     "Microservice interface design defaults to strict RESTful standards (verb-object structure, semantic HTTP status codes). I only consider introducing GraphQL when facing front-end scenarios requiring heavy aggregation queries."
     ),
    ("root.work",
     "Manual execution of database schema changes is strictly prohibited. They must be managed using versioned migration tools like Flyway or Liquibase, ensuring that the DDL in every environment is traceable and rollbackable."
     ),
    ("root.work",
     "Log printing conventions: Production environments globally default to INFO level, retaining only state transitions and critical paths; Dev/Test environments have DEBUG enabled; ERROR level logs must include full stack traces and request contexts."
     ),
    ("root.work",
     "Monitoring and alerting rules: Thresholds must be dynamically adjusted based on the actual SLA promised by the business, with alert convergence configured (e.g., similar errors within 5 minutes only trigger one alert). I extremely detest 'cry wolf' invalid alerts."
     ),
    ("root.work",
     "Before executing a production release, a Smoke Test based on the core P0 flow must be completed in the pre-release environment. Only after verifying the main transaction pipeline is clear is the actual deployment allowed."
     ),
    ("root.work",
     "When encountering a P-level production incident, a post-mortem meeting must be held within 48 hours of resolution. The doc must record the Timeline, root cause (using the 5 Whys), and most importantly, yield actionable Action Items."
     ),
    ("root.work",
     "When dealing with tech debt (like hardcoding or outdated dependencies), I make it a habit to create a dedicated Tech Debt Epic in Jira for tracking, squeezing out 10%-20% of capacity in every sprint to pay it off rather than mixing it with business requirements."
     ),
    ("root.work",
     "For cross-frontend-backend or cross-team collaboration, I stick to 'contract first': Both parties must align on API fields and Mock data on the API management platform, reaching a consensus before entering parallel development."
     ),
    ("root.work",
     "Code commenting philosophy: I firmly believe good code explains the 'What'. Therefore, comments should only explain the 'Why' (e.g., weird logic bypassing a specific bug, or special business rules)."
     ),
    ("root.work",
     "Git branching strategy: The main branch (main/master) is strictly protected against force pushes. All daily development is done on feature/xxx branches pulled from main, merged exclusively via PRs."
     ),
    ("root.work",
     "PR/MR descriptions must follow a template: including business context (linked Jira ticket), brief overview of core changes, and local testing results. If there are front-end changes, UI comparison screenshots or screen recordings are mandatory."
     ),
    ("root.work",
     "Before starting any performance optimization, the first step is always to collect baseline data using tools (like JProfiler/Chrome DevTools). Upon completion, a 'before-and-after throughput/latency comparison report' must be provided."
     ),
    ("root.work",
     "SonarQube or similar security scanning tools must be mandatorily integrated into the CI/CD pipeline. If High/Critical vulnerabilities or hardcoded secrets are detected, the build process is immediately blocked."
     ),
    ("root.work",
     "Third-party library upgrade strategy: The last Wednesday of every month is set as 'Dependency Checkup Day' to evaluate and incrementally upgrade non-breaking packages, avoiding disastrous major version jumps caused by years of neglect."
     ),
    ("root.work",
     "All non-confidential architecture design and API documentation should preferably use Markdown and be stored directly in the docs/ folder of the code repository. This achieves 'docs follow code' and inherently provides version control."
     ),
    ("root.work",
     "If a meeting I host or participate in exceeds 1 hour, a mandatory 5-10 minute biological break must be scheduled halfway through to prevent participants from losing focus and lowering discussion efficiency."
     ),
    ("root.work",
     "For daily communication, I strongly prefer asynchronous methods (like sending Feishu docs or leaving emails). I dislike frequent instant voice calls or 'nudges' that interrupt my flow state. Synchronous communication is reserved only for urgent blockers."
     ),
    ("root.work",
     "When receiving a large Epic requirement, I habitually use mind maps to break it down into sub-tasks. In principle, every leaf-node task should not exceed 2 working days in granularity to ensure easy progress tracking."
     ),
    ("root.work",
     "When facing a technical blocker or environment issue, I set a rule to 'try solving it independently for 1 hour first' (checking official docs, searching GitHub Issues) before asking for help. If still unresolved, I organize reproduction steps before reaching out."
     ),
    ("root.work",
     "Departmental weekly meetings should only be used to sync on cross-team key milestones, major decisions, or commendations. Detailed project execution and routine progress updates must be read asynchronously via docs before the meeting."
     ),
    ("root.work",
     "As a grass-roots manager or core member, I insist on having a 1-on-1 chat with close colleagues or subordinates once a month. To ensure quality, I prepare 2-3 open-ended topics in advance (e.g., recent pain points, career development)."
     ),
    ("root.work",
     "For personal promotion and performance review materials, I habitually accumulate assets (especially quantifiable benefit data) monthly in my weekly reports or a separate Notion page, firmly resisting the practice of slapping a PPT together at the year-end deadline."
     ),
    ("root.work",
     "Internal team sharing frequency: I require myself to give a tech or business presentation at least once a quarter. This is not just for team building, but also to force myself to thoroughly digest fuzzy knowledge using the 'Feynman Technique'."
     ),
    ("root.work",
     "When onboarding a new hire as a Mentor, I never rush to explain code details in the first week. Instead, I spend half a day drawing diagrams of the business overview, profit models, and historical tech debt to help them build a holistic view of the business."
     ),
    ("root.work",
     "Uniform team code formatting (spaces, indentation, casing) relies strictly on automated Linter tools like ESLint/Checkstyle to enforce checks upon code commit. We absolutely do not waste human Code Review time nitpicking formatting."
     ),
    ("root.work",
     "Unit testing requirements: I don't blindly chase 100% coverage across the project, but for modules involving financial calculations, state transitions, or core algorithms, branch coverage must strictly exceed 80% to be merged."
     ),
    ("root.work",
     "End-to-End (E2E) testing strategy: Primarily focus automated scripts on high-frequency core user flows (like login and main checkout flow). Edge cases are left to manual exploratory testing to maximize ROI."
     ),
    ("root.work",
     "Full-link stress testing is preferably conducted in a staging/stress-test environment scaled equivalently to production. If done in production, it can only be low-volume canary traffic during off-peak hours, strictly avoiding impact on real users."
     ),
    ("root.work",
     "Strict adherence to the Twelve-Factor App principle of 'strict separation of config from code'. Sensitive information like database passwords and third-party API tokens are never written in config files; they must be injected via environment variables or a Vault system."
     ),
    ("root.work",
     "Managing multi-environment configs: I advocate that all environments (Dev/Test/Prod) share the same config Schema template. Only during the CD phase do placeholders get replaced with environment-specific values to prevent missing configurations."
     ),
    ("root.work",
     "Production deployment strategy: No-downtime releases are mandatory. I fully utilize Blue-Green deployment or K8s-based Canary releases. If monitoring probes detect anomalies, a one-click rollback to the last stable version within 3 minutes is guaranteed."
     ),
    ("root.work",
     "Microservice health check standards: Liveness probes only check if the process is alive. Readiness probes must not only check the service itself but also verify if fundamental dependencies like DB/Redis are ready; otherwise, traffic is rejected."
     ),
    ("root.work",
     "Graceful Shutdown of services: Upon receiving a SIGTERM signal, the service must first reject new requests and wait up to 30 seconds for current executing threads to finish before releasing resources and exiting the process."
     ),
    ("root.work",
     "In complex microservice architectures, the gateway layer is forced to generate a unified Trace ID, which must be passed down to every downstream service and database via MDC logs or request headers, facilitating SkyWalking troubleshooting later."
     ),
    ("root.work",
     "Global error code design: Must have a unified standard (e.g., 5 digits: 2 for the business line + 3 for the specific error). Vague 'System Error' throws are rejected. Every error code must have a corresponding troubleshooting guide in the documentation."
     ),
    ("root.work",
     "Regarding user tickets or raw feedback from the production environment, the dev team must provide an initial response or troubleshooting direction within 24 hours. Bugs severely impacting customer experience are prioritized equivalently to P0 incidents."
     ),
    ("root.work",
     "When facing temporary requirement changes late in the review process, I don't just agree verbally. I force the PM to record the timestamp, reason, and expected ROI of the change in the original PRD or Jira to serve as a decision snapshot for future retrospectives."
     ),
    ("root.work",
     "Before starting core technical initiatives (like introducing new middleware or large-scale refactoring), an RFC review involving at least 2 Senior Engineers must be organized to fully expose potential single points of failure and performance bottleneck risks."
     ),
    ("root.work",
     "System architecture evolution philosophy: I advocate for 'small, rapid iterations and localized refactoring' (evolutionary approach). I'm extremely vigilant against and opposed to 'Big Bang' rewrites from scratch to minimize the risk of business stagnation."
     ),
    ("root.work",
     "Maintaining a personal tech radar: Every six months, I review the lifecycle of my current tech skills in my personal notes, tagging which frameworks I need to 'Adopt', which to 'Assess', and which have been 'Put on hold/Deprecated'."
     ),
    ("root.work",
     "Principles for participating in Open Source: I don't submit meaningless typo fixes just to farm commits. I prioritize discovering bugs in OSS projects heavily used by myself or my company, submitting practical bug fixes or features."
     ),
    ("root.work",
     "Ways to maintain technical sensitivity: I force myself to output at least one deep-dive technical article monthly on my personal blog or Yuque. Whether it's documenting pitfalls or analyzing source code, the goal is to practice explaining complex problems clearly."
     ),
    ("root.work",
     "Workflow for learning new middleware/frameworks: I never stop at reading the documentation. I must write a runnable Demo executing CRUD or core features locally. Only after validating feasibility do I decide whether to introduce it to business projects."
     ),
    ("root.work",
     "Documenting major technical choices: Before introducing any non-mainstream new tech, a complete ADR (Architecture Decision Record) must be written, comparing at least three competitors in detail and listing the trade-offs of the final choice for future maintainers."
     ),
    ("root.work",
     "Professionalism in resignation/project handovers: No verbal handovers. A comprehensive Wiki including system architecture, deployment processes, legacy traps, and core account credentials must be organized two weeks in advance, with business comments added to complex logic blocks."
     ),
    ("root.work",
     "Precipitating team's common knowledge: I strongly demand abandoning the habit of sending files in WeChat groups or using local Word documents. All team knowledge must land on centralized Wiki platforms with directory structures and global search capabilities like Confluence or Notion."
     ),
    ("root.work",
     "Password security bottom line: All work and personal account passwords are generated as high-strength random strings by password managers like 1Password/Bitwarden. The extremely dangerous 'one password rules them all' behavior is strictly eliminated."
     ),
    ("root.work",
     "Authentication hardening: For core systems containing sensitive assets like GitHub, AWS Console, and Bastion Hosts, 2FA (Two-Factor Authentication) is mandatorily enabled. I'd rather look at an authenticator code every time than compromise."
     ),
    ("root.work",
     "Auditing sensitive data operations: Any DB deletions, schema changes, or large asset adjustments in the admin backend must automatically log the operator, IP, timestamp, and JSON snapshots of before/after changes at the code level, ensuring traceability."
     ),
    ("root.work",
     "Data disaster recovery strategy: For self-hosted databases, I insist on executing 'daily incremental backup + Sunday early morning full backup', asynchronously syncing cold backup data encrypted to low-frequency cloud storage (like OSS/S3)."
     ),
    ("root.work",
     "Disaster Recovery drills: Just having backups isn't enough. I require a full-process DR drill once a quarter over the weekend to verify if backup files are corrupted and if the recovery time is within the RTO (Recovery Time Objective)."
     ),

    # --- root.personal Personal Life (64 items) ---
    ("root.personal",
     "Upon waking up at 6:30 AM, the first thing I do is drink about 300ml of warm water (preferably 40 degrees Celsius) to awaken the digestive tract and replenish moisture lost overnight, before proceeding to wash up."
     ),
    ("root.personal",
     "My biological clock is fixed to waking up naturally around 6:30 AM. This period is completely free from external interruptions, making it the golden time for deep thinking and planning the day's critical tasks."
     ),
    ("root.personal",
     "Exercise routine maintained at least 3 times a week, alternating between a 5km jog and 40 minutes of freestyle swimming. The focus is on maintaining cardiopulmonary function and relieving stress, not pursuing competitive results."
     ),
    ("root.personal",
     "Nighttime sleep ritual: 1 hour before bed (after about 22:30), I put my phone far away and switch to reading physical books or a Kindle to avoid blue light suppressing melatonin secretion."
     ),
    ("root.personal",
     "On sunny weekends, I strongly prefer going for a 10km hike in forest parks far from the city center or undeveloped suburbs, craving a 'digital detox' in a natural environment."
     ),
    ("root.personal",
     "Daily diet adheres to a light principle: I strongly reject greasy and salty takeout. When ordering, I always leave a note for 'less oil and less salt', and ensure at least 50% of each meal consists of leafy green vegetables."
     ),
    ("root.personal",
     "A severe coffee addict: I only drink pure iced Americanos or Yirgacheffe pour-overs. I refuse any overly fancy coffee drinks with added syrups, non-dairy creamers, or excessive flavorings."
     ),
    ("root.personal",
     "Accommodation preference for non-business trips: I ditch standardized, cookie-cutter chain hotels and prefer picking characteristic homestays (Airbnb) that have kitchens and blend into the local community vibe."
     ),
    ("root.personal",
     "Extremely restrained napping habits: To prevent waking up groggy from deep sleep and to avoid messing up the nighttime sleep rhythm, I strictly set an alarm for 25-30 minutes for afternoon naps."
     ),
    ("root.personal",
     "No matter how rushed the morning is, I insist on eating breakfast. It's usually quick overnight oatmeal or two slices of whole wheat toast with black coffee, providing a stable blood sugar source for the whole morning."
     ),
    ("root.personal",
     "Quantified hydration management: I always keep a 1-liter marked water bottle on my desk, forcing myself to finish two full bottles (approx. 2 liters) during work hours to maintain metabolism."
     ),
    ("root.personal",
     "Anti-sedentary intervention: I've set a sedentary reminder on my smartwatch. Every 45 minutes of work, I am forced to get up to fetch water or go to the restroom, taking 5 minutes to stretch my cervical and lumbar spine."
     ),
    ("root.personal",
     "Strict adherence to the 20-20-20 eye care rule: For every 20 minutes staring at the screen, I force myself to look away at green plants or distant views 20 feet (about 6 meters) away for at least 20 seconds to relieve ciliary muscle spasms."
     ),
    ("root.personal",
     "Weekend boundaries: I require myself to spend at least one full day on the weekend 'completely offline'. I turn off work app push notifications and do not reply to non-urgent work group messages, returning to real life."
     ),
    ("root.personal",
     "Rational consumption mechanism: When encountering non-daily consumables I want to buy (like electronics or clothes), I force myself to put them in a 'cooling-off list' in my notes. I only place the order if I still find it necessary and within budget 7 days later."
     ),
    ("root.personal",
     "Practicing minimalism: At the end of every quarter over a weekend, I conduct a thorough 'decluttering' of the whole house. Clothes unworn for half a year and dust-collecting electronics are listed on Xianyu or donated to keep the physical space clean."
     ),
    ("root.personal",
     "Micro-financial management: Every night before going to sleep, I spend 3 minutes opening my accounting app (like Qianji) to categorize and record the day's WeChat/Alipay expenses, keeping an absolute sensitivity to cash flow."
     ),
    ("root.personal",
     "Macro asset allocation preference: I don't touch high-risk short-term stock trading. A fixed percentage of my monthly surplus funds is used to regularly invest in CSI 300 and S&P 500 index funds, acting as a long-termist."
     ),
    ("root.personal",
     "Personal risk hedging: Knowing health is the capital of revolution, I've early on equipped myself with million-dollar medical insurance, critical illness insurance, and term life insurance to ensure I don't drag down family finances in extreme scenarios."
     ),
    ("root.personal",
     "Financial security baseline: I always keep an 'F**k you money' (emergency fund) equivalent to 6 months of daily expenses in a checking account or easily withdrawable money market fund to cope with sudden unemployment or illness."
     ),
    ("root.personal",
     "Reading medium preference: For social sciences or classic literature requiring deep thought, I insist on buying physical books to enjoy the tactile feel of turning pages; for practical or reference books, I use WeChat Read for easy highlighting and note exporting."
     ),
    ("root.personal",
     "Reading pacing: I don't blindly chase the vanity of 'reading 100 books a year'. I maintain a steady pace of thoroughly reading 2-3 books a month, and it's not considered finished until I've written a short review or a mind map."
     ),
    ("root.personal",
     "Film/TV aesthetic preferences: Immune to mindless popcorn blockbusters. I heavily favor logically rigorous suspense/crime films, hardcore sci-fi, and high-quality nature/history documentaries produced by the BBC."
     ),
    ("root.personal",
     "Music scenario binding: When entering a 'flow' state for work, my headphones loop Bach's classical music, lazy jazz, or Lo-fi beats. I absolutely cannot have pop music with human vocals interfering with my thought process."
     ),
    ("root.personal",
     "Gaming preferences: I have zero interest in high-intensity, heavy-social competitive mobile games like Honor of Kings. I am exclusively passionate about immersive, macro-narrative single-player 3A masterpieces like Zelda or The Witcher 3."
     ),
    ("root.personal",
     "Casual photography habits: I don't like carrying heavy DSLRs when going out, believing a flagship camera phone is enough. My lens is mostly pointed at street light and shadow, architectural lines, or natural scenery, rarely taking selfies."
     ),
    ("root.personal",
     "Social energy pool management: A typical introverted personality (Type I). Extremely averse to noisy bars or large 50-person KTV team-building events, much preferring deep 1-on-1 conversations with 2-3 close friends in a quiet cafe."
     ),
    ("root.personal",
     "Refusing social friction: When attending unavoidable gatherings, if I feel my energy draining or the topics uninteresting, I politely find an excuse to leave early, completely unburdened by psychological guilt or awkwardness."
     ),
    ("root.personal",
     "Gift-giving values: I believe the core of gifting is matching needs. I never give flashy but useless ornamental items, usually opting for high-quality practical consumables (like aromatherapy, good coffee beans) or a massage/experience voucher."
     ),
    ("root.personal",
     "Self-definition of holidays: Going back to my hometown to accompany my parents during the Spring Festival is an ingrained ritual; however, I take my own birthdays very lightly, satisfied with just a bowl of longevity noodles or a small cake."
     ),
    ("root.personal",
     "Pet inclination assessment: Down to my bones, I am a true 'cat person', appreciating a cat's independent boundaries. However, considering my current living environment and travel frequency, out of responsibility, I've decided to postpone adoption for now."
     ),
    ("root.personal",
     "Home aesthetic standards: Deeply infatuated with Nordic minimalist style or Japanese Wabi-Sabi. I insist on the 'less is more' principle, keeping surfaces as empty as possible and leaving more physical space for air and light."
     ),
    ("root.personal",
     "Indoor greenery preferences: I like adding a touch of life indoors, but know I lack patience. Thus, I only keep extremely drought-tolerant plants like Snake Plants, Monstera, and Bird of Paradise that require watering only once a week or half a month."
     ),
    ("root.personal",
     "Housework cleaning flow: I stick to the micro-habit of 'putting things back immediately', spending 10 minutes daily keeping countertops clear; Every Sunday, I allocate exactly 1.5 hours for a deep clean: mopping, dusting, and changing bed sheets."
     ),
    ("root.personal",
     "Laundry rules: Strictly separating dark clothes from whites into different laundry baskets. To free up energy, 90% of my clothes are made of materials that can be directly machine-washed and dried, desperately avoiding delicate fabrics requiring handwashing or dry cleaning."
     ),
    ("root.personal",
     "Working adult's dining strategy: I spend half a day on weekends Meal Prepping, washing, chopping, and portion-freezing meat and vegetables; on weekday nights, I just need a simple stir-fry or microwave heating, saving time while staying healthy."
     ),
    ("root.personal",
     "Weekday takeout survival guide: When absolutely too busy and forced to order takeout, my menu radar automatically filters out heavy/greasy options like BBQ or fried chicken, directly locking onto low-calorie light salads, brown rice poke bowls, or light Japanese set meals."
     ),
    ("root.personal",
     "Snack reserve principles: Chips and spicy gluten (Latiao) will never appear in my office drawer. I only stock plain mixed nuts (a handful daily for unsaturated fats) and fresh seasonal fruits, strictly controlling free sugar intake."
     ),
    ("root.personal",
     "Attitude towards tipsiness and drinking culture: Extremely disgusted by drinking table culture and the hangovers from high-proof liquor. I only sip a glass of dry red wine or fruity craft beer alone on a good weekend night, knowing when to stop."
     ),
    ("root.personal",
     "Tea preferences: For daily hydration and refreshment, I prefer green tea like Pre-Qingming Longjing, or floral/fruity Oolong (like Dancong or Tieguanyin). Even at milk tea shops, I only order pure tea; my highest tolerance is 'no extra sugar' fresh milk tea."
     ),
    ("root.personal",
     "Harsh sleep environment requirements: Extremely sensitive to light and noise. The bedroom must be installed with 100% blackout curtains, requiring absolute silence when sleeping, and the AC is kept year-round at a slightly cool 18-22 degrees Celsius."
     ),
    ("root.personal",
     "Bedding pickiness (Neck-friendly): Tossed all overly soft synthetic pillows, exclusively using a slow-rebound memory foam neck pillow of moderate height that perfectly supports the physiological curve of the cervical spine."
     ),
    ("root.personal",
     "Bedding pickiness (Back-friendly): Cannot tolerate soft beds where the whole body sinks in. The mattress must be a firmer pocket-spring or high-density coir mat to ensure sufficient lumbar support when lying on my back."
     ),
    ("root.personal",
     "Loungewear attitude: The moment I get home, I must take off restrictive outdoor clothes. Pajamas and loungewear are strictly 100% cotton or modal, demanding an absolutely loose fit for a frictionless, skin-friendly feel."
     ),
    ("root.personal",
     "Solidified Morning Routine: Morning actions have formed muscle memory: wake up & drink warm water -> wash face & brush teeth -> 20 mins yoga stretch or jog -> quick breakfast -> walk out the door listening to a podcast. It cannot be randomly disrupted."
     ),
    ("root.personal",
     "Solidified Evening Routine: Pre-sleep landing ritual: reply to the last necessary message and wrap up -> hot shower -> lie in bed reading a physical book for 30 mins -> put on an eye mask and fall asleep."
     ),
    ("root.personal",
     "Mindfulness and Meditation habits: After morning washing up or before bed, I spend 10 minutes doing focused breathing meditation using Headspace or Tide apps, clearing brain cache and lowering the day's cortisol levels."
     ),
    ("root.personal",
     "Long-form reflection mechanism: Every Sunday night, I open my Notion 'Weekly Retrospective' template and, like a diary, record the emotional highs and lows of the week, memorable small things, and expectations for the next week."
     ),
    ("root.personal",
     "Micro positive psychology intervention: No matter how terrible the day went, right before sleeping, I list 3 'good things' that happened today in my mind (or memo), even if it's just 'drank a great cup of coffee'."
     ),
    ("root.personal",
     "Emergency exit for negative emotions: When I notice myself sinking into depression or anxiety, I never stay cooped up in my room alone. My first resort is immediately putting on running shoes to sweat it out, or finding a trusted close friend to vent."
     ),
    ("root.personal",
     "High-pressure period strategy: When work projects are overwhelmingly heavy and stress is peaking, I consciously practice 'physical isolation' on weekends. I decline all unnecessary gatherings, leaving my schedule blank at home to let my thoughts wander freely."
     ),
    ("root.personal",
     "Annual leave planning philosophy: I try my best to avoid traveling during national golden weeks like May Day or National Day when crowds peak. I always take off-peak annual leave a week before or after the holidays, enjoying cheaper flights/hotels and better experiences."
     ),
    ("root.personal",
     "The ultimate meaning of travel: Hate the 'sleep on the bus, take photos off the bus' commando-style checklist tourism. I aim for 'slow travel' scheduling only 1-2 spots a day, willing to spend an entire afternoon sitting at a corner cafe spacing out and people-watching."
     ),
    ("root.personal",
     "Geek-style luggage packing: Extremely loathe dragging heavy checked suitcases. I've long prepared a standard 'Travel Essentials Checklist' and travel light with just a single backpack every time, bringing mostly quick-dry clothing."
     ),
    ("root.personal",
     "Long-distance transport preference sorting: For trips under 5 hours, high-speed rail is the top choice (spacious seats, stable network, no need to go to suburban airports 2 hours early); flights are only a backup for cross-provincial long hauls."
     ),
    ("root.personal",
     "Hard standards for remote accommodation: When picking a hotel, the most important thing isn't luxurious decoration, but 'must be within 500 meters of a subway station' and 'no complaints about poor soundproofing in reviews'. Cleanliness and quietness are the bottom lines."
     ),
    ("root.personal",
     "Deep integration into destinations: Upon arriving in an unfamiliar city, I dislike commercialized pedestrian streets. Instead, I make sure to visit the largest local morning wet market or do a purposeless City Walk in the old town."
     ),
    ("root.personal",
     "Travel imagery preferences: The lens is rarely pointed at myself (almost no landmark selfies). The photo album is filled with peculiar architectural structures abroad, stray cats on streets, mottled tree shadows, or macro close-ups of local cuisine."
     ),
    ("root.personal",
     "Souvenir ideology: Firmly refuse to buy cheap fridge magnets with place names or useless tourist ornaments. I'm more inclined to buy local specialty snacks/condiments from supermarkets or a practical canvas bag with local design elements."
     ),
    ("root.personal",
     "Major bodily maintenance: I put a comprehensive annual health checkup as a top-priority yearly task. Besides standard metrics, I add cervical spine MRIs or thyroid/breast ultrasounds targeting occupational diseases of programmers."
     ),
    ("root.personal",
     "Dental health investment: I insist on teeth cleaning at least once a year and require the dentist to do a full cavity check. Knowing well that 'a small hole ignored leads to immense pain later', I book restorations immediately upon finding minor cracks or early-stage cavities."
     ),
    ("root.personal",
     "Long-term ophthalmology tracking: Because I rely heavily on screens, I go to a formal eye hospital annually for visual acuity and fundus examinations. Once astigmatism or myopia worsens, I immediately update my lenses to reduce compensatory eye fatigue."
     ),
    ("root.personal",
     "Scientific epidemic prevention attitude: Never blindly tough it out. During the autumn-winter transition, I always book a flu vaccine in advance; for mature adult vaccines like HPV or Shingles, I also schedule them according to plan."
     ),
    ("root.personal",
     "Survival skills reserve: I haven't just watched first aid videos; I actually signed up to get a Red Cross basic first responder certificate (including CPR and AED usage), and I do retraining every two years just in case."
     ),

    # --- root.learning Learning Related (64 items) ---
    ("root.learning",
     "English input habits: During the 30 minutes of washing up and commuting every morning, I habitually play non-fiction English podcasts (like NPR or TechCrunch) aiming to maintain a feel for the language environment and listening acuity."
     ),
    ("root.learning",
     "Technical book reading funnel: When getting a new book, I never chew through it word by word from page one. I first spend 15 minutes scanning the TOC, preface, and conclusion to confirm the specific pain points it solves, then decide whether to deep-read selected chapters or just keep it as a reference manual."
     ),
    ("root.learning",
     "The first law of picking up a new framework: Before drowning in dazzling articles about principles, I must first run the Quick Start / Tutorial provided in the official docs from start to finish on my local machine. Only after seeing 'Hello World' do I dive deeper."
     ),
    ("root.learning",
     "Personal knowledge base medium preference: All study notes must be written in plain text Markdown. This not only guarantees cross-platform compatibility but also facilitates easy historical version management and diffing using Git."
     ),
    ("root.learning",
     "Technical deadlock breaking mechanism: When encountering weird errors during coding or environment setup, I set a 'stubbornness cap' of 20 minutes. If I'm totally clueless after that, I must get up to clear my head or ask colleagues/StackOverflow for help."
     ),
    ("root.learning",
     "Motivation for continuous output: I require myself to submit at least one complete small feature PR for my Side Project (like an open-source tool or blog theme) over the weekend to maintain the sense of accomplishment of creating."
     ),
    ("root.learning",
     "Ultimate practice of the Feynman Technique: Firmly believing 'you only truly understand it if you can write it out in plain English'. When facing particularly complex low-level mechanisms (like JVM Garbage Collection), I prefer verifying my mastery by drawing diagrams and writing an accessible blog post."
     ),
    ("root.learning",
     "Programming language learning strategy: Abandoning boring syntax books. When learning a new language (like Rust or Go), I dive straight in with a small actual requirement (e.g., writing a CLI bulk file renamer) and fill in knowledge gaps on the fly."
     ),
    ("root.learning",
     "Video tutorial bingeing strategy: When watching tech-sharing videos on Bilibili or YouTube, to combat long-winded preludes, I default to 1.5x speed; I only switch back to normal speed and take screenshots during core code demonstrations."
     ),
    ("root.learning",
     "Criteria for selecting online courses: Extremely repelled by courses that just read off PPTs. Excellent courses must meet three criteria: accurate subtitles, runnable source code for lessons, and hands-on exercises for each chapter."
     ),
    ("root.learning",
     "Personal skill tree development path: Following the 'T-shaped' principle. First establishing a breadth of cognitive understanding across the entire software engineering domain (Frontend, Backend, DevOps, QA), and then picking a niche (like high-concurrency backend or cloud-native) to dig deeply into."
     ),
    ("root.learning",
     "Frontend vs Backend energy allocation: My career positioning is focused on backend engineering and architectural evolution, but I demand of myself the foundational ability to write Vue/React components, reaching the passing mark of 'being able to independently build an internal admin dashboard'."
     ),
    ("root.learning",
     "Algorithm coding touch maintenance: I don't blindly grind LeetCode just for interviews, but weekly I will hand-type 2-3 medium difficulty classic problems (like Dynamic Programming or Graph Theory), purely to maintain logical thinking agility."
     ),
    ("root.learning",
     "System Design training method: Besides reading classic case studies, I prefer taking out pen and paper or using Excalidraw to draw data flow diagrams, trying to explain the peak-shaving and valley-filling principles of a flash-sale system to non-technical friends."
     ),
    ("root.learning",
     "Database skill moat: I consider mastering SQL and its execution plan tuning as the survival baseline for backend engineers; as for various NoSQL DBs (like MongoDB, Neo4j), I adopt a 'learn on demand, search when needed' strategy."
     ),
    ("root.learning",
     "Obsession with underlying network protocols: Knowing well that existing HTTP libraries abstract things beautifully, I still force myself to capture packets to deeply understand the underlying byte-stream principles of TCP 3-way handshakes, congestion control, and HTTP/2 multiplexing."
     ),
    ("root.learning",
     "Reverence for OS fundamentals: Even though I code in high-level languages daily, I insist on reviewing OS basics like process/thread scheduling models and virtual memory paging, viewing them as the foundation for troubleshooting production CPU spikes or OOM mysteries."
     ),
    ("root.learning",
     "Distributed systems theory primer: I treat the CAP theorem and Raft/Paxos consensus protocols as the 'inner martial arts' of microservice architectures, regularly revisiting related papers to avoid making assumptions that violate laws of physics when designing high-availability systems."
     ),
    ("root.learning",
     "Cloud-native toolkit positioning: My attitude towards Docker containerization and K8s orchestration is 'not seeking to be a K8s ops expert, but must be proficient in writing Dockerfiles and basic Deployment/Service YAML scripts'."
     ),
    ("root.learning",
     "Preemptive security awareness: I demand that I not only write functionally correct code but also master the attack principles and defensive coding standards of the OWASP Top 10 (like XSS, CSRF, SQLi) to avoid digging holes."
     ),
    ("root.learning",
     "Deliberate practice of Soft Skills: Realizing that tech is just a tool and communication is the lubricant. I consciously rotate practicing my documentation skills for tech proposals, communication skills in requirement reviews, and public speaking in team meetings."
     ),
    ("root.learning",
     "Dual-track technical English: Currently, reading English official docs and source code comments is seamless without translation software; but spoken English is still under deliberate practice, targeting fluent participation in multinational open-source meetings."
     ),
    ("root.learning",
     "Self-requirement for writing outputs: No matter how busy, I must produce a long-form text output on Yuque or a personal blog every week. Even if it's not cutting-edge, like documenting pits I fell into this week, the emphasis is on building a habit of structured writing."
     ),
    ("root.learning",
     "Desensitization therapy for public speaking fear: I actively volunteer to my Leader to do a 30-minute tech sharing session within the team quarterly. By forcing myself to prepare PPTs and face audience questions, I gradually eliminate the nervousness of public speaking."
     ),
    ("root.learning",
     "The art of listening and questioning: In technical discussions or meetings, I constantly remind myself to 'shut up first and interrupt less'. After the other person fully expresses their point, I frequently use follow-up questions like 'Do you mean... is that correct?' to align understanding."
     ),
    ("root.learning",
     "Golden rule of giving feedback: When doing Code Reviews or evaluating others' work, never use emotional terms like 'this is written terribly'. Feedback must 'specifically point out the line of code', 'provide actionable improvement suggestions', and 'be timely and friendly'."
     ),
    ("root.learning",
     "The ritual of project closure: Regardless of whether a launched project won an award or caused a disaster, a detailed Post-mortem document must be written during the wrap-up phase, distilling 3 reusable experiences or red lines to prevent repeating mistakes."
     ),
    ("root.learning",
     "Effective structure of reading notes: Abandoning pure 'highlighting' style excerpts. Every reading note must contain three parts: an excerpt of the original core argument + reflections linked to personal experience + Action Items I will immediately execute after reading."
     ),
    ("root.learning",
     "Personal knowledge network construction: Using bi-directional linking note tools like Obsidian or Logseq. Abandoning rigid hierarchical folders, adopting 'atomized tagging + bidirectional linking + regular review roaming' to manage fragmented knowledge."
     ),
    ("root.learning",
     "Ultimate metric for learning outcome (Feynman Technique): After studying a complex concept (like why Kafka is fast), if I can't explain it in plain terms to a humanities major friend, it proves I only know the surface and need to relearn it."
     ),
    ("root.learning",
     "Application of anti-forgetting tools: Deeply aware that the human brain is unreliable. For parameters or architectural facts that must be memorized but are critically important, I import them into software like Anki, utilizing Spaced Repetition algorithms for periodic review."
     ),
    ("root.learning",
     "Deliberate practice breaking out of the comfort zone: When realizing I am particularly weak in an area (like writing complex regular expressions), I no longer avoid it. Instead, I dedicate a weekend spending 5 concentrated hours on specific exercises until I conquer it."
     ),
    ("root.learning",
     "Setting up a high-flow learning environment: To enter deep study, the physical environment must be stringent: phone on Do Not Disturb and in a drawer, noise-canceling headphones playing white noise, and preferably a whiteboard nearby for drawing logic diagrams anytime."
     ),
    ("root.learning",
     "Time allocation based on brain rhythms: Through long-term experimentation, I found my mind is clearest from 7-9 AM, specifically reserved for chewing on the hardest low-level principles or algorithm problems; while afternoons are prone to drowsiness, so I schedule writing repetitive practice code or organizing notes."
     ),
    ("root.learning",
     "Micro-focus management: When studying dry theory, I heavily rely on the Pomodoro Technique. Strictly adhering to 25 minutes of full-attention reading; any stray thoughts popping up are jotted down on scratch paper, then I enjoy a guilt-free 5-minute break."
     ),
    ("root.learning",
     "Resisting the temptation of Multitasking: Deeply knowing that context switching in the brain causes huge overhead. Thus, when studying, only one full-screen IDE or doc is left on the monitor, tackling one specific knowledge point at a time."
     ),
    ("root.learning",
     "Peer power to break information silos: When tackling a difficult certification exam or massive framework, I look for 1-2 peers with the same goal in tech groups to form a check-in group, using peer pressure to combat personal laziness."
     ),
    ("root.learning",
     "Strategies for finding and asking a Mentor: When stuck on an architectural design dilemma for a long time, I never stubbornly hold out to save face. After organizing my current thoughts and attempted solutions, I proactively consult experienced seniors in the team; usually, a single sentence from them awakens me."
     ),
    ("root.learning",
     "Open source connections to maintain cutting-edge sensitivity: Besides keeping my head down and working, I regularly browse GitHub Trending leaderboards or lurk in high-quality tech WeChat groups to see what new wheels people are discussing, avoiding working in a silo."
     ),
    ("root.learning",
     "Panning for gold in tech conferences: Faced with overwhelming tech salons, I only register for sessions where the topics directly address my current pain points or have hands-on code demos. I firmly decline purely conceptual or marketing-driven vendor pitches."
     ),
    ("root.learning",
     "Purchasing rules for tech books: Any tech book heavily involving specific frameworks or code examples is only bought in digital form (PDF/Kindle) for easy command copying and full-text searching; only timeless conceptual classics are bought physically for collection."
     ),
    ("root.learning",
     "Reading strategy for English Papers: I don't start translating the dense body text right away. I first spend 5 minutes skimming the Abstract and Conclusion to judge if its research direction provides reference value for my current work, then decide whether to read the experiment section closely."
     ),
    ("root.learning",
     "Documentation lookup priority sequence: Encountering an unknown API, the first priority is always to consult the most authoritative, up-to-date official original documentation. Only when official docs are vague do I look into CSDN or personal blogs for others' pit-filling experiences."
     ),
    ("root.learning",
     "Hardcore source code reading methodology: Firmly opposed to chewing source code line-by-line without prioritization. It must be driven by a specific question (e.g., 'How does Spring solve circular dependencies?'), utilizing IDE breakpoints to follow the trail, only looking at the core trunk."
     ),
    ("root.learning",
     "Scientific steps for Bug Debugging: Forcing myself to quit the bad habit of 'blindly guessing and modifying code'. Strictly following: 1. Create a stable reproduction environment -> 2. Use binary search code commenting to narrow down suspects -> 3. View call stacks for final positioning."
     ),
    ("root.learning",
     "Log defense line construction philosophy: When writing business code, I imagine myself as the future troubleshooter. Logs must be injected on critical paths involving external system calls or state machine transitions, and the original Exception stack must always be preserved in Catch blocks."
     ),
    ("root.learning",
     "First principles of Performance Optimization: Keep Donald Knuth's maxim in mind: 'Premature optimization is the root of all evil.' Without concrete performance bottleneck data obtained via flame graphs or stress testing tools, I never blindly introduce complex caching or async designs for a few milliseconds' gain."
     ),
    ("root.learning",
     "Test-Driven Development (TDD) application scenarios: When developing new, independent modules with complex logic and many edge cases (like a billing rule engine), I try writing assertion test cases first, then the implementation code; but for legacy spaghetti code, I only add the most basic regression tests before refactoring."
     ),
    ("root.learning",
     "The Boy Scout Rule for daily Refactoring: Refactoring is absolutely not stopping business to work on it for a month exclusively. Rather, when submitting new features, I conveniently clean up nearby code smells (like long methods, magic numbers), ensuring the code left behind is cleaner than when I found it."
     ),
    ("root.learning",
     "Pragmatic understanding of Design Patterns: Memorizing UML diagrams for the 23 design patterns is meaningless. The core lies in deeply understanding the 'Open-Closed Principle' or 'Single Responsibility' intents behind them. When code truly exhibits scalability pain points, the pattern naturally surfaces."
     ),
    ("root.learning",
     "Pragmatic architectural design view: Deeply aware that architecture is the art of compromise. I adhere to 'Simplicity is beauty' and 'Evolutionary and just enough', extremely repulsed by over-engineering behaviors like forcefully applying dragon-slaying skills like Microservices or Service Mesh on projects with less than 1,000 DAU."
     ),
    ("root.learning",
     "Code quality 3D ranking: During daily coding, I always hold a scale in my mind: First, ensure code 'Readability' (humans can understand it), secondly 'Maintainability' (easy to extend), and lastly, for non-core high-traffic APIs, squeeze out extreme 'Performance'."
     ),
    ("root.learning",
     "Stubbornness with variable naming: I'd rather spend 5 minutes thinking of a super long camelCase name with accurate business semantics (like userHasCompletedKYCCheck) than use vague abbreviations (like uchk) or meaningless magic numbers. Code is documentation."
     ),
    ("root.learning",
     "Physical boundary control of functions: Obsessively following the 'Single Responsibility Principle'. Once a method exceeds one screen of code (about 50 lines), or deeply nested if-else blocks appear inside, I immediately feel the urge to extract private methods."
     ),

    # --- root.ideas Ideas / Inspiration (64 items) ---
    ("root.ideas",
     "Conceptualizing a personal notes tool based on local LLMs and vector embeddings: When inputting fragmented thoughts, the system automatically extracts semantics and builds weak links with past notes via a knowledge graph, breaking the constraints of traditional tree-structured directories."
     ),
    ("root.ideas",
     "Want to develop a scaffolding tool that reads Git commit history, Jira state transitions, and Feishu/Slack schedules, calling an LLM API over the weekend to summarize a structured weekly report draft with one click, saving 80% of weekly report writing time."
     ),
    ("root.ideas",
     "Ultimate tagging system design draft for personal knowledge bases: Ditching chaotic synonyms, strictly using a 2D matrix tagging system—i.e., [Domain Tag] (like #Architecture) +[Project Lifecycle] (like #WIP/ProjectA), supplemented with auto-archiving timestamps."
     ),
    ("root.ideas",
     "Thinking of a solution for the pain point of consolidating 'fragmented inputs' in WeChat's File Transfer Assistant: Could I write a WeChat bot leveraging AI to auto-determine if a sentence is a task, diary entry, or inspiration, and route it to the respective Notion DB via API."
     ),
    ("root.ideas",
     "Attempting to bridge preference data and personal workflows: Envisioning a central automation script that syncs with 'meeting states' in the calendar to automatically mute the phone, pause casual chat notifications on the PC, and push 'read-it-later' articles to the top of the to-do list."
     ),
    ("root.ideas",
     "Exploring representing a personal tech cognitive map using a Graph Database (like Neo4j). Nodes are knowledge points, edges are dependencies or similarities, visually revealing which tech branches still have severe blind spots."
     ),
    ("root.ideas",
     "Dissatisfied with current cloud note latency, want to design a 'Local-First' note syncing scheme: Based on CRDT (Conflict-free Replicated Data Type) algorithms, enabling instant open-and-edit in network-less subways, with seamless multi-device merging upon reconnection."
     ),
    ("root.ideas",
     "Natural language query UX for a personal memory vault: Instead of typing exact keywords in a search box, build a ChatGPT-like dialog. Asking 'What brand was the monitor I bought last Singles Day?', the system directly gives the answer via RAG retrieval of purchase records."
     ),
    ("root.ideas",
     "Using AI to end meaningless docstring labor: Conceptualizing an IDE plugin that, before committing code, analyzes the Abstract Syntax Tree (AST) and method context to auto-generate Javadoc/Docstrings containing parameter explanations and business 'Why's via LLM."
     ),
    ("root.ideas",
     "Automated solution to tech docs always drifting from code: Trying to write API docs directly within code annotations. Adding a CI pipeline step to parse the AST, extract changes, and push to platforms like Swagger or internal Wikis automatically, achieving strong version binding."
     ),
    ("root.ideas",
     "Conceptualizing an API backwards-compatibility automated checker: At the Microservice Contract Testing level, comparing the new and old OpenAPI Schema before merging PRs. If required fields are deleted or types are changed, it directly blocks the merge."
     ),
    ("root.ideas",
     "How to quantify the blast radius of dependency upgrades? I want to write a script that not only analyzes Maven/NPM package dependency trees but also combines it with the code call chain to generate a visual heat map marking exactly which business APIs are impacted by upgrading a core library."
     ),
    ("root.ideas",
     "Feeling powerless against massive ELK logs: Want to introduce a log anomaly pattern recognition algorithm (based on clustering machine learning). It learns normal log stream patterns during peace times; if a specific format of Error logs suddenly deviates from the baseline, it immediately triggers a high-priority alert."
     ),
    ("root.ideas",
     "User behavior analytics shouldn't just be for PMs: Want to build a visual Kanban in the backend for devs to see real-time click funnel conversions of the Feature they just deployed, using real data feedback to elevate devs' business intuition."
     ),
    ("root.ideas",
     "A/B testing configs are always a mess: Envisioning a 'Code as Config' solution. Defining experiment buckets directly in business code via annotations, auto-generating the experiment console, and integrating with APM tools to auto-output latency comparison reports across versions."
     ),
    ("root.ideas",
     "Intelligent canary traffic routing strategy based on business thresholds: When canarying a new version, don't just blindly route 5% of traffic. Dynamically monitor CPU load and error rates; if metrics are stable for 5 minutes, auto-escalate the canary ratio stepwise to 20%, then 50%."
     ),
    ("root.ideas",
     "Multi-environment config misses constantly cause disasters: Considering writing a CLI tool specifically to perform semantic-level diffs on Dev/Test/Prod configs fetched from remote config centers (like Nacos/Apollo), highlighting variables missing or misspelled in Production."
     ),
    ("root.ideas",
     "Painless rollback design for DB Schema changes: Exploring combining Liquibase and GitOps. For every DDL commit, forcefully require a reverse rollback.sql. In an online disaster, a single command rolls back both the DB table structure and the code to the previous version simultaneously."
     ),
    ("root.ideas",
     "Frontend waiting for backend APIs is too painful: Can we use LLMs to parse JSON examples or table definitions in requirement docs and one-click generate an advanced Mock Server with boundary value exception and latency simulations? Allowing true physical parallel development."
     ),
    ("root.ideas",
     "E2E UI tests are too expensive to maintain (DOM changes break them): Researching the introduction of Self-Healing mechanisms. When the original XPath fails to find an element, the framework uses AI computer vision or contextual understanding to auto-locate the actual button and heal the script."
     ),
    ("root.ideas",
     "Performance degradation is often a boiled frog situation: Conceptualizing adding 'Performance Baseline Regression Testing' to the CI pipeline. Standard load tests run on core APIs every midnight; if throughput drops 10% below the historical baseline for 3 consecutive days, a P1 Jira defect is auto-generated."
     ),
    ("root.ideas",
     "Security scanning shouldn't stop at 'raising problems without fixing': Want to combine vulnerability scanners like Trivy/Snyk with LLMs. Upon finding a CVE, it doesn't just warn, but directly opens an automated Pull Request updating the dependency version or patching the logic."
     ),
    ("root.ideas",
     "Salvation from spaghetti code: Conceptualizing a smart refactoring assistant. Not just finding copy-pasted duplicate code, but identifying design pattern-level code smells and auto-providing concrete code comparison suggestions like 'Extract Superclass' or 'Replace if-else with Strategy Pattern'."
     ),
    ("root.ideas",
     "Tech debt shouldn't just be a slogan: Attempting to build a quantifiable tech-improvement priority model. Comprehensively evaluating a legacy module's 'modification frequency (Git Blame)', 'number of triggered online Bugs', and 'refactoring cost' to calculate an ROI score, guiding targeted debt repayment."
     ),
    ("root.ideas",
     "Team knowledge often gets lost in word of mouth: Envisioning a team-internal Knowledge Graph Q&A bot built by scraping the team's Wiki, Jira comments, and code commit history. A newbie asks 'Who knows the payment module's FX calculations best?', and the bot @'s the right person based on code contribution."
     ),
    ("root.ideas",
     "Breaking the cycle of cross-project reinventing the wheel: Developing an AST probe tool that scans across repositories, auto-extracting best practice snippets like 'phone number masking' or 'pagination querying' and recommending them in team chats to push for base component extraction."
     ),
    ("root.ideas",
     "Landing scenarios for AI-assisted Code Review: Letting LLMs do the first pass of Review before humans. Focusing on checking for missing null checks, potential concurrency deadlocks, or Catastrophic Backtracking in regex (ReDoS), lightening the Reviewer's load."
     ),
    ("root.ideas",
     "Ultimate Traceability from requirement to implementation: Building a data chain connecting a PRD requirement -> Jira task -> Git Commit -> CI Build ID -> Deployed Docker layer. Upon a bug, instantly reverse-tracing to the person who proposed the requirement."
     ),
    ("root.ideas",
     "Automated Runbook for root cause analysis: When a DB deadlock alert triggers, the monitoring system shouldn't just send a notification. It should auto-trigger a script, grab the slow SQL, Thread Dumps, and active connections at that instant, packaging them into a troubleshooting report sent with the alert."
     ),
    ("root.ideas",
     "Capacity planning without guesswork: Researching time-series forecasting algorithms (like Prophet) combined with historical mega-sale traffic curves to automatically generate accurate replica scaling prediction models for each microservice node for the next Double 11."
     ),
    ("root.ideas",
     "Automated patrol for Cloud resource cost optimization: Writing a cron job to scan AWS/AliCloud accounts daily, finding zombie instances with CPU < 5% over the past 7 days or unattached Elastic IPs, auto-generating an 'Estimated Savings' report pushed to the DevOps lead."
     ),
    ("root.ideas",
     "Multi-cloud architectural abstraction against vendor lock-in: Discussing building a unified Terraform/Pulumi abstraction layer between applications and infra. Whether running on AWS or Tencent Cloud, deployment scripts remain identical, enabling true multi-cloud DR and traffic routing."
     ),
    ("root.ideas",
     "Edge computing & Central cloud synergy exploration: Envisioning high-density IoT scenarios where ultra-low latency data cleansing and lightweight inference are pushed to edge nodes (like factory gateways). Only aggregated high-value state data is asynchronously uploaded to the central cloud to save bandwidth costs."
     ),
    ("root.ideas",
     "Ultra-low latency optimization for real-time data pipelines: When evaluating a Flink + Kafka streaming architecture, considering how adjusting Batch Sizes and utilizing Zero-Copy tech can squeeze end-to-end processing latency from seconds down to hundreds of milliseconds."
     ),
    ("root.ideas",
     "Unified retrieval paradigm for multi-modal data: In a personal knowledge base, I want to unify vectorization of text notes, meeting audio recordings, and PPT screenshots into Milvus. Achieving the magical experience of 'searching with one sentence and pulling up that specific architecture diagram and that audio clip'."
     ),
    ("root.ideas",
     "Breaking the cold start dilemma in personalized recommendation systems: Thinking about how, lacking historical click data, we can leverage LLMs to perform deep semantic expansion on a few interest tags filled out by new users, quickly generating a high-quality initial item pool."
     ),
    ("root.ideas",
     "Compromise solutions for Privacy Protection and AI Training: Researching the feasibility of Federated Learning in medical or financial scenarios. Model parameters are calculated locally at each institution, exchanging only encrypted gradients, achieving 'data is usable but invisible' joint modeling."
     ),
    ("root.ideas",
     "Pragmatic blockchain implementation in non-financial scenarios: Setting crypto aside, conceptualizing how to use the immutability of Smart Contracts to build a multi-party trusted traceability and proof-of-existence system for agricultural products or expensive drugs' supply chains, solving information silo trust issues."
     ),
    ("root.ideas",
     "AR/VR's dimensional strike on boring training scenarios: Envisioning developing a virtual equipment maintenance system based on Apple Vision Pro, transforming complex industrial manuals into 3D floating overlays guiding operations, allowing zero-experience novices to execute precision tasks step-by-step."
     ),
    ("root.ideas",
     "Acoustic confrontation in Voice UI scenarios: Conceptualizing how to combine traditional microphone array beamforming tech with the latest Deep Learning noise suppression models (like RNNoise) to strip away subway background noise, vastly improving voice command recognition accuracy."
     ),
    ("root.ideas",
     "Precision optimization for vertical domain multi-lingual translation: General translators fail at tech jargon. Planning to Fine-tune open-source models by feeding massive bilingual open-source code comments and RFC docs to create a geek-exclusive translation engine for programmers."
     ),
    ("root.ideas",
     "Breaking the ultimate difficulty in PDF parsing: The biggest pain in doc understanding is poorly formatted tables. Exploring combining OCR and layout analysis models (LayoutLM) to accurately reconstruct structured JSON data from complex borderless tables with merged cells."
     ),
    ("root.ideas",
     "AI-driven closed-loop Unit Test generation: Not just letting LLMs generate core logic tests, but connecting it to coverage tools. If an edge branch is found uncovered, it automatically feeds back to the LLM, demanding supplementary boundary test cases for specific input parameters."
     ),
    ("root.ideas",
     "Solving the 'Goldfish Memory' problem in Dialog Systems: For complex, multi-turn continuous dialogues, exploring maintaining a dynamically compressed Context Tree in memory. When token limits are exceeded, it prioritizes pruning small-talk nodes, permanently retaining the user's core preferences."
     ),
    ("root.ideas",
     "Building a team Prompt Engineering asset library: Realized making LLMs output stable JSONs for business is highly technical. Planning to build a GitHub-like Prompt template repository internally, supporting version control, A/B testing, and performance scoring."
     ),
    ("root.ideas",
     "The biggest pain point of Supervised Fine-Tuning (SFT) is data labeling: Want to build an annotation assistant based on Active Learning. A smaller model does pre-labeling; humans only correct data with low confidence scores, boosting annotation efficiency tenfold."
     ),
    ("root.ideas",
     "Explaining AI 'Hallucinations' to users: In rigorous domains like finance, conceptualizing RAG system outputs that not only give answers but display floating highlights in the UI tracing the conclusion exactly back to specific sentences in internal docs, providing OCD-level explainability."
     ),
    ("root.ideas",
     "Exploring new paradigms for Human-Machine Collaboration: Abandoning the traditional Q&A mode. Envisioning a GitHub Copilot Workspace-like UX where AI first outputs a detailed draft execution plan, allowing humans to modify/intervene at nodes before clicking execute to generate the final output."
     ),
    ("root.ideas",
     "Task breakdown and execution framework for Agents: Researching how a macro-command (like 'Help me research competitor pricing on the market and generate a chart') is broken down by a Master Agent, orchestrating Search Agents, Crawler Agents, and Data Analysis Agents to aggregate results."
     ),
    ("root.ideas",
     "Anti-deadlock orchestration for Multi-Agent collaboration: When multiple Agents interact in a virtual sandbox, conceptualizing a 'Watchdog' mechanism akin to OS process scheduling. If two Agents loop arguing about a topic for over 3 turns, mandatory intervention cuts the circuit."
     ),
    ("root.ideas",
     "Core tech to elevate RAG retrieval recall quality: Relying purely on text vector distance is far from enough. Thinking of introducing 'Reranker models'. After vectors pre-filter the Top 20 docs, a deep cross-attention model performs precise sorting, pushing the most relevant to the #1 spot."
     ),
    ("root.ideas",
     "Hybrid evolution of Vector Database retrieval strategies: Facing different query types, exploring implementing a Hybrid Search architecture—using Dense vectors for semantic similarity while retaining traditional BM25 Sparse retrieval to ensure specialized domain vocabulary isn't lost."
     ),
    ("root.ideas",
     "The strongest combination of Knowledge Graphs and LLMs (GraphRAG): Exploring during the KB embedding phase, not just extracting Chunks, but letting the model automatically extract entities to build sub-graphs. Retrieving multi-hop info along relationship networks to answer global statistical or cross-timeline questions LLMs struggle with."
     ),
    ("root.ideas",
     "Robust design for Agent Tool Calling: When an AI calls a weather API that returns 502 or times out, it shouldn't just crash. Envisioning an auto-recovery strategy demanding the LLM analyze the error, modify parameters to retry, or switch to fallback endpoints."
     ),
    ("root.ideas",
     "Extreme UX optimization for Streaming outputs: When generating Markdown or code blocks, the frontend often glitches due to truncated tags. Researching adding a micro buffer-parser on the frontend to smoothly render incomplete syntax trees while receiving data streams."
     ),
    ("root.ideas",
     "Utilization strategies for massive million-token Context Windows: Discussing how to front-load a 500-page developer manual as a Prompt. At the same time, exploring how to mitigate the 'Lost in the middle' phenomenon for middle contents via positional encoding optimizations."
     ),
    ("root.ideas",
     "Landing Knowledge Distillation on geek devices: How to extract and transfer the reasoning power of a 70B behemoth into a 7B small model, letting it run smoothly locally on a MacBook, or even directly deployed on edge devices like Raspberry Pi or smartphones."
     ),
    ("root.ideas",
     "Accelerating LLM Inference and reducing costs: Digging deep into Quantization (like GGUF, AWQ) and KV Cache optimization tech. Thinking about how to slash VRAM usage from 32GB to 8GB at the cost of a tolerable 1% precision loss, achieving local inference freedom on consumer-grade GPUs."
     ),
    ("root.ideas",
     "Multi-model routing strategies for high-concurrency scenarios: In production, we shouldn't stubbornly use the same LLM. Envisioning a smart gateway routing simple translation requests to fast/cheap open-source small models, and only routing complex logical reasoning tasks to expensive GPT-4 class models."
     ),
    ("root.ideas",
     "Building a closed-loop for model evaluation: Saying goodbye to subjective 'feeling-based' evaluation. Conceptualizing an A/B testing system based on automated eval sets and human scoring. Any Fine-tuning or Prompt update must pass baseline benchmarks before being merged into the main branch."
     ),
    ("root.ideas",
     "Flywheel effect of driving model evolution via real user feedback: Collecting 'thumbs down' or 'regenerate' events from product UIs, recording these Bad Cases into DBs, and periodically feeding them to the model using preference optimization algorithms (like DPO/RLHF), making the system increasingly understand the team's niche business."
     ),
    ("root.ideas",
     "Validating the necessity of building vertical-domain proprietary LLMs: General LLMs are like undergrads who know a lot but lack depth. Thinking about curating 10 years of private code and exclusive research reports to pre-train a 'PhD student' model that purely understands core financial trading logic or medical imaging diagnostics."
     ),
    ("root.ideas",
     "Application imagination of On-device AI (Small models): What can offline AI do? Envisioning running a 100MB footprint intent-recognition model on the lock screen, instantly turning on the flashlight or opening a payment code via voice in a basement with zero cellular signal."
     ),
    ("root.ideas",
     "Returning from tech fanaticism to AI Security baselines: LLMs are easily bypassed by 'Prompt Injection' to extract secrets. Conceptualizing deploying a dedicated Guardrails model at the gateway layer to real-time filter malicious user instructions and harmful model outputs."
     )
]
