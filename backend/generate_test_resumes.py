import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

OUTPUT_DIR = Path(r"e:\Resume screnner\sample_resumes")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESUMES = [
    # =========================================================================
    # 1. AI / MACHINE LEARNING (5 Resumes)
    # =========================================================================
    {
        "filename": "Aarav_Sharma_AI_LLM_Engineer.pdf",
        "name": "Aarav Sharma",
        "title": "Senior AI & LLM Engineer",
        "email": "aarav.sharma@example.com",
        "phone": "+1 (555) 234-5678",
        "location": "San Francisco, CA",
        "summary": "Senior AI Engineer with over 6 years of professional experience specializing in Generative AI, LLM fine-tuning, RAG pipelines, and vector databases. Proven track record deploying scalable AI services into production using PyTorch and FastAPI.",
        "skills": [
            "Programming: Python, C++, SQL, Bash",
            "AI/ML: PyTorch, LangChain, LlamaIndex, RAG, Hugging Face, Transformers",
            "Vector DBs: ChromaDB, Pinecone, FAISS",
            "Cloud & DevOps: Docker, Kubernetes, AWS, FastAPI, Git, CI/CD"
        ],
        "experience": [
            {
                "role": "Lead Generative AI Engineer",
                "company": "Nexus AI Labs",
                "period": "2022 - Present",
                "bullets": [
                    "Architected and deployed enterprise RAG pipeline serving 500,000 monthly queries using LangChain, ChromaDB, and OpenAI models.",
                    "Fine-tuned open-source LLMs using PyTorch on AWS EC2 GPU clusters, improving response precision by 28%.",
                    "Developed high-throughput FastAPI microservices containerized with Docker and orchestrated on Kubernetes."
                ]
            },
            {
                "role": "Machine Learning Engineer",
                "company": "Cognitive Solutions",
                "period": "2018 - 2022",
                "bullets": [
                    "Engineered end-to-end NLP pipelines for automated document classification and sentiment analysis using Python and Hugging Face.",
                    "Implemented vector similarity search reducing latency by 45% using FAISS index structures."
                ]
            }
        ],
        "projects": [
            {"name": "Enterprise DocuChat", "desc": "Context-aware conversational RAG assistant using LangChain, ChromaDB, and Python FastAPI."},
            {"name": "Neural Query Router", "desc": "Semantic vector search engine with hybrid re-ranking and sub-second response times."}
        ],
        "education": "Master of Science in Computer Science, Stanford University (2018)"
    },
    {
        "filename": "Sophia_Chen_ML_Engineer.pdf",
        "name": "Sophia Chen",
        "title": "Machine Learning Engineer",
        "email": "sophia.chen@example.com",
        "phone": "+1 (555) 345-6789",
        "location": "Seattle, WA",
        "summary": "Machine Learning Engineer with 4 years of experience building predictive models, computer vision systems, and automated ML pipelines. Highly skilled in TensorFlow, Scikit-learn, MLOps, and AWS cloud deployment.",
        "skills": [
            "Languages: Python, SQL, R",
            "ML Frameworks: TensorFlow, PyTorch, Scikit-learn, OpenCV",
            "Data & MLOps: Pandas, NumPy, MLflow, Docker, AWS Sagemaker",
            "Databases: PostgreSQL, MySQL, Redis"
        ],
        "experience": [
            {
                "role": "Machine Learning Engineer",
                "company": "VisionTech Analytics",
                "period": "2021 - Present",
                "bullets": [
                    "Trained and deployed deep learning object detection models using TensorFlow and OpenCV with 94% accuracy.",
                    "Built automated MLOps model training and evaluation pipelines using MLflow and Docker.",
                    "Collaborated with data engineering teams to optimize feature stores in PostgreSQL and Redis."
                ]
            },
            {
                "role": "Junior Data Scientist",
                "company": "DataSphere Corp",
                "period": "2020 - 2021",
                "bullets": [
                    "Developed classification and regression models using Python and Scikit-learn to forecast customer churn.",
                    "Wrote automated data cleaning and preprocessing scripts with Pandas and NumPy."
                ]
            }
        ],
        "projects": [
            {"name": "DefectDetector", "desc": "Real-time industrial anomaly detection system using TensorFlow and OpenCV."},
            {"name": "Automated Churn Predictor", "desc": "Gradient-boosted customer churn prediction model deployed via AWS Sagemaker."}
        ],
        "education": "Bachelor of Science in Data Science, University of Washington (2020)"
    },
    {
        "filename": "Marcus_Vance_NLP_Data_Scientist.pdf",
        "name": "Marcus Vance",
        "title": "NLP Data Scientist",
        "email": "marcus.vance@example.com",
        "phone": "+1 (555) 456-7890",
        "location": "Boston, MA",
        "summary": "Data Scientist with 3 years of hands-on experience in Natural Language Processing, text summarization, and statistical modeling. Experienced with Python, BERT, PyTorch, SQL, and data visualization.",
        "skills": [
            "Core: Python, SQL, Statistics, Data Analysis",
            "NLP & ML: Natural Language Processing, BERT, PyTorch, NLTK, spaCy, Hugging Face",
            "Libraries: Pandas, NumPy, Scikit-learn, Matplotlib, Seaborn",
            "Tools: Git, Linux, Jupyter, Docker"
        ],
        "experience": [
            {
                "role": "NLP Specialist & Data Scientist",
                "company": "LexiCore Systems",
                "period": "2022 - Present",
                "bullets": [
                    "Fine-tuned BERT transformer models for clinical record entity extraction, achieving 91% F1 score.",
                    "Built conversational intent recognition pipelines using spaCy, NLTK, and PyTorch.",
                    "Extracted insights from unstructured text datasets exceeding 10 million rows using SQL and Pandas."
                ]
            },
            {
                "role": "Associate Data Analyst",
                "company": "Beacon Analytics",
                "period": "2021 - 2022",
                "bullets": [
                    "Conducted statistical analyses and generated interactive data dashboards for executive stakeholders.",
                    "Developed Python web scrapers to gather unstructured market intelligence text."
                ]
            }
        ],
        "projects": [
            {"name": "ClinicalNER", "desc": "Named entity extraction model for medical notes using Hugging Face Transformers."},
            {"name": "TopicRadar", "desc": "Unsupervised semantic clustering tool for user feedback using TF-IDF and PyTorch embeddings."}
        ],
        "education": "Master of Science in Computational Linguistics, Boston University (2021)"
    },
    {
        "filename": "Priya_Patel_Junior_AI_Researcher.pdf",
        "name": "Priya Patel",
        "title": "Junior AI Researcher",
        "email": "priya.patel@example.com",
        "phone": "+1 (555) 567-8901",
        "location": "Austin, TX",
        "summary": "Motivated Junior AI Researcher with 1.5 years of experience in computer vision, deep learning algorithms, and scientific research. Proficient in Python, PyTorch, OpenCV, and mathematical optimization.",
        "skills": [
            "Programming: Python, C++, MATLAB",
            "Machine Learning: PyTorch, OpenCV, Scikit-learn, Deep Learning",
            "Math & Theory: Linear Algebra, Statistics, Calculus, Optimization",
            "Tools: Git, Linux, Jupyter Notebooks"
        ],
        "experience": [
            {
                "role": "AI Research Assistant",
                "company": "Frontier AI Institute",
                "period": "2023 - Present",
                "bullets": [
                    "Assisted in training deep convolutional neural networks for semantic image segmentation using PyTorch.",
                    "Benchmarked image augmentation techniques using OpenCV to boost model generalization on low-resource datasets.",
                    "Authored research documentation and reproduced state-of-the-art vision models from academic papers."
                ]
            }
        ],
        "projects": [
            {"name": "Autonomous Lane Guide", "desc": "Edge-deployed lane detection model using OpenCV and PyTorch."},
            {"name": "Neural Style Transfer Studio", "desc": "Interactive neural artistic transfer application built with Python."}
        ],
        "education": "Bachelor of Science in Computer Science, UT Austin (2023)"
    },
    {
        "filename": "Liam_OConnor_Generative_AI_Specialist.pdf",
        "name": "Liam O'Connor",
        "title": "Generative AI & Prompt Engineer",
        "email": "liam.oconnor@example.com",
        "phone": "+1 (555) 678-9012",
        "location": "New York, NY",
        "summary": "Generative AI Specialist with 2 years of professional experience in prompt engineering, LLM orchestration, evaluation metrics, and AI workflow integration. Skilled in LangChain, Python, OpenAI APIs, and ChromaDB.",
        "skills": [
            "AI Engineering: Prompt Engineering, LangChain, OpenAI, LLM, RAG",
            "Languages & Frameworks: Python, FastAPI, JavaScript, REST API",
            "Vector Stores: ChromaDB, Pinecone",
            "Tools: Git, Postman, Docker"
        ],
        "experience": [
            {
                "role": "Generative AI Engineer",
                "company": "OmniBotics Tech",
                "period": "2023 - Present",
                "bullets": [
                    "Designed system prompt architectures and few-shot reasoning workflows for customer service LLMs.",
                    "Integrated LangChain agents with external REST APIs and ChromaDB knowledge bases.",
                    "Established automated unit testing to evaluate model hallucinations and output consistency."
                ]
            }
        ],
        "projects": [
            {"name": "SupportCopilot", "desc": "Automated email draft generation tool with guardrail evaluation."},
            {"name": "PromptBench", "desc": "Benchmarking harness for comparing latency and quality across frontier LLM models."}
        ],
        "education": "Bachelor of Arts in Cognitive Science, Columbia University (2022)"
    },

    # =========================================================================
    # 2. SOFTWARE DEVELOPMENT (5 Resumes)
    # =========================================================================
    {
        "filename": "Alex_Rivera_Full_Stack_Developer.pdf",
        "name": "Alex Rivera",
        "title": "Senior Full Stack Developer",
        "email": "alex.rivera@example.com",
        "phone": "+1 (555) 789-0123",
        "location": "Chicago, IL",
        "summary": "Full Stack Developer with 5 years of experience delivering robust web applications. Expert in React, TypeScript, Node.js, FastAPI, PostgreSQL, and Docker. Adept in modern microservices and agile workflows.",
        "skills": [
            "Frontend: React, TypeScript, JavaScript, HTML, CSS, Next.js, Redux",
            "Backend: Node.js, Python, FastAPI, Express, REST API, GraphQL",
            "Databases: PostgreSQL, MongoDB, Redis",
            "DevOps & Tools: Docker, Git, CI/CD, AWS, Agile, Scrum"
        ],
        "experience": [
            {
                "role": "Senior Full Stack Engineer",
                "company": "Apex Web Solutions",
                "period": "2021 - Present",
                "bullets": [
                    "Engineered responsive customer web portal in React and TypeScript with 99.9% uptime for 200,000 active users.",
                    "Designed backend microservices using FastAPI and Node.js connected to PostgreSQL databases.",
                    "Standardized Docker development environments, reducing new developer onboarding time by 60%."
                ]
            },
            {
                "role": "Full Stack Developer",
                "company": "Kinetix Digital",
                "period": "2019 - 2021",
                "bullets": [
                    "Developed RESTful APIs and UI dashboards using React, Node.js, and MongoDB.",
                    "Configured continuous integration pipelines using Git and automated testing suites."
                ]
            }
        ],
        "projects": [
            {"name": "CloudFleet Manager", "desc": "SaaS vehicle tracking web dashboard with real-time WebSockets and React."},
            {"name": "FastCommerce API", "desc": "High-performance ecommerce REST API built with FastAPI and PostgreSQL."}
        ],
        "education": "Bachelor of Science in Software Engineering, University of Illinois (2019)"
    },
    {
        "filename": "David_Kim_Backend_Engineer.pdf",
        "name": "David Kim",
        "title": "Senior Backend Engineer",
        "email": "david.kim@example.com",
        "phone": "+1 (555) 890-1234",
        "location": "San Jose, CA",
        "summary": "Senior Backend Engineer with 7 years of experience architecting distributed, low-latency microservices. Deep expertise in Go, Python, PostgreSQL, Redis, Kafka, Docker, and Kubernetes.",
        "skills": [
            "Languages: Go, Golang, Python, SQL, C++",
            "Backend: Microservices, REST API, gRPC, FastAPI, Django",
            "Data & Messaging: PostgreSQL, Redis, Kafka, MySQL",
            "Cloud: Docker, Kubernetes, AWS, Linux, CI/CD"
        ],
        "experience": [
            {
                "role": "Principal Backend Architect",
                "company": "Stratus Financial",
                "period": "2020 - Present",
                "bullets": [
                    "Engineered distributed ledger transaction service in Go capable of handling 20,000 requests per second.",
                    "Replaced monolithic backend with scalable Kubernetes microservices, cutting server compute costs by 35%.",
                    "Optimized PostgreSQL schema and connection pooling with Redis caching to drop p99 latency to 18ms."
                ]
            },
            {
                "role": "Backend Software Engineer",
                "company": "Quantix Software",
                "period": "2017 - 2020",
                "bullets": [
                    "Built Python FastAPI services and event-driven data streaming pipelines with Apache Kafka.",
                    "Enforced code quality through test-driven development and CI/CD automation."
                ]
            }
        ],
        "projects": [
            {"name": "GoStream Core", "desc": "Ultra-low-latency event streaming engine written in Go and backed by Kafka."},
            {"name": "Distributed Rate Limiter", "desc": "Fault-tolerant sliding window rate limiter implemented in Redis and Python."}
        ],
        "education": "Master of Science in Computer Science, UC Berkeley (2017)"
    },
    {
        "filename": "Elena_Rostova_Frontend_Developer.pdf",
        "name": "Elena Rostova",
        "title": "Frontend React Specialist",
        "email": "elena.rostova@example.com",
        "phone": "+1 (555) 901-2345",
        "location": "Denver, CO",
        "summary": "Creative Frontend Developer with 4 years of experience building accessible, responsive, and aesthetically pleasing single-page web applications. Specialized in React, TypeScript, JavaScript, CSS, and Next.js.",
        "skills": [
            "Frontend: React, TypeScript, JavaScript, HTML, CSS, Next.js, Redux, Tailwind",
            "Design & UI: Responsive Design, Glassmorphism, CSS Grid, Figma, Storybook",
            "Tools: Git, Webpack, Vite, npm, REST API"
        ],
        "experience": [
            {
                "role": "Lead Frontend Developer",
                "company": "PixelCraft Studios",
                "period": "2021 - Present",
                "bullets": [
                    "Led frontend engineering for an enterprise analytics dashboard in React, TypeScript, and Vite.",
                    "Implemented custom design system and component library with 100% WCAG accessibility compliance.",
                    "Reduced initial page bundle size by 42% through code-splitting, lazy loading, and asset optimization."
                ]
            },
            {
                "role": "Frontend Web Developer",
                "company": "Vivid Media",
                "period": "2020 - 2021",
                "bullets": [
                    "Created interactive marketing landing pages using HTML, CSS, JavaScript, and React.",
                    "Integrated frontend components with backend REST APIs."
                ]
            }
        ],
        "projects": [
            {"name": "Aura Design System", "desc": "Reusable React component library with themes and automated testing."},
            {"name": "DataGlow Visualizer", "desc": "Interactive financial chart visualization application in TypeScript and D3."}
        ],
        "education": "Bachelor of Science in Interactive Media & Computing, CU Boulder (2020)"
    },
    {
        "filename": "Carlos_Mendez_Java_Developer.pdf",
        "name": "Carlos Mendez",
        "title": "Senior Java & Spring Boot Developer",
        "email": "carlos.mendez@example.com",
        "phone": "+1 (555) 012-3456",
        "location": "Dallas, TX",
        "summary": "Enterprise Software Engineer with 6 years of experience developing mission-critical backend systems. Expert in Java, Spring, Spring Boot, MySQL, REST API, Docker, and Apache Kafka.",
        "skills": [
            "Languages: Java, SQL, Python",
            "Frameworks: Spring, Spring Boot, Hibernate, REST API, Microservices",
            "Databases: MySQL, PostgreSQL, Oracle",
            "Architecture: Kafka, Docker, Kubernetes, Jenkins, Maven, Git, Agile"
        ],
        "experience": [
            {
                "role": "Senior Java Developer",
                "company": "OmniBank Global",
                "period": "2020 - Present",
                "bullets": [
                    "Designed secure payment processing microservices using Java 17 and Spring Boot.",
                    "Integrated Apache Kafka for real-time transaction event publication across internal banking services.",
                    "Tuned Hibernate ORM queries and MySQL indexes to resolve database deadlocks."
                ]
            },
            {
                "role": "Software Engineer",
                "company": "Enterprise Tech Solutions",
                "period": "2018 - 2020",
                "bullets": [
                    "Maintained core enterprise Java application backend and wrote JUnit regression tests.",
                    "Created automated Jenkins build pipelines and containerized artifacts with Docker."
                ]
            }
        ],
        "projects": [
            {"name": "PayGateway Microservice", "desc": "PCI-compliant payment transaction router built with Java and Spring Boot."},
            {"name": "EventStream Broker", "desc": "Kafka message consumer orchestrator processing high-volume banking telemetry."}
        ],
        "education": "Bachelor of Science in Computer Engineering, UT Dallas (2018)"
    },
    {
        "filename": "Ananya_Roy_Junior_Software_Engineer.pdf",
        "name": "Ananya Roy",
        "title": "Junior Software Engineer",
        "email": "ananya.roy@example.com",
        "phone": "+1 (555) 123-7890",
        "location": "Atlanta, GA",
        "summary": "Enthusiastic Junior Software Engineer with 1.5 years of experience in full stack software development. Skilled in Python, JavaScript, Django, HTML, CSS, SQL, and Git.",
        "skills": [
            "Languages: Python, JavaScript, SQL, HTML, CSS",
            "Frameworks: Django, Flask, Bootstrap",
            "Databases: SQLite, PostgreSQL",
            "Tools: Git, GitHub, Linux, VS Code, REST API"
        ],
        "experience": [
            {
                "role": "Associate Software Engineer",
                "company": "Novus Technologies",
                "period": "2023 - Present",
                "bullets": [
                    "Developed web application features and RESTful endpoints using Python, Django, and PostgreSQL.",
                    "Constructed responsive HTML and CSS interfaces and assisted with cross-browser manual testing.",
                    "Participated in daily Agile standups and resolved backend bug tickets in GitHub."
                ]
            }
        ],
        "projects": [
            {"name": "TaskPilot App", "desc": "Collaborative project management web app built using Django and SQLite."},
            {"name": "PriceTracker Bot", "desc": "Python web scraping application providing automated price alerts via email."}
        ],
        "education": "Bachelor of Science in Computer Science, Georgia Tech (2023)"
    },

    # =========================================================================
    # 3. DEVOPS, CLOUD & DATA ENGINEERING (5 Resumes)
    # =========================================================================
    {
        "filename": "Vikram_Malhotra_DevOps_Architect.pdf",
        "name": "Vikram Malhotra",
        "title": "Senior DevOps & Cloud Architect",
        "email": "vikram.malhotra@example.com",
        "phone": "+1 (555) 234-8901",
        "location": "Raleigh, NC",
        "summary": "DevOps Architect with 8 years of experience designing secure, highly available cloud infrastructures. Master of AWS, Docker, Kubernetes, Terraform, CI/CD, and Linux automation.",
        "skills": [
            "Cloud: AWS, Azure, GCP",
            "Containers & Orchestration: Docker, Kubernetes, Helm",
            "IaC & Automation: Terraform, Ansible, Bash, Python",
            "CI/CD & Monitoring: Jenkins, GitHub Actions, Prometheus, Grafana, Linux"
        ],
        "experience": [
            {
                "role": "Principal Cloud DevOps Architect",
                "company": "CloudScale Enterprises",
                "period": "2020 - Present",
                "bullets": [
                    "Architected multi-region AWS infrastructure with Terraform and Kubernetes hosting 50+ enterprise services.",
                    "Built automated GitHub Actions CI/CD deployment pipelines, cutting release cycle times from weeks to minutes.",
                    "Instituted Prometheus and Grafana observability stack with proactive alerting."
                ]
            },
            {
                "role": "Senior DevOps Engineer",
                "company": "InfraCore Solutions",
                "period": "2016 - 2020",
                "bullets": [
                    "Migrated on-premise Linux server farm into containerized AWS Docker environments.",
                    "Automated system configuration and package management using Ansible playbooks."
                ]
            }
        ],
        "projects": [
            {"name": "KubeDeploy Automation", "desc": "Terraform module library deploying production-grade EKS clusters on AWS."},
            {"name": "ZeroDowntime Pipeline", "desc": "Blue-green deployment continuous integration workflow with automated rollbacks."}
        ],
        "education": "Bachelor of Technology in Information Technology, IIT Kharagpur (2016)"
    },
    {
        "filename": "Sarah_Jenkins_SRE.pdf",
        "name": "Sarah Jenkins",
        "title": "Site Reliability Engineer (SRE)",
        "email": "sarah.jenkins@example.com",
        "phone": "+1 (555) 345-9012",
        "location": "Portland, OR",
        "summary": "Site Reliability Engineer with 5 years of experience ensuring 99.99% system availability across distributed microservices. Specialized in Linux, Kubernetes, Ansible, Prometheus, Python, and incident response.",
        "skills": [
            "Reliability & Systems: SRE, Linux, Kubernetes, Ansible",
            "Monitoring: Prometheus, Grafana, Datadog, ELK Stack",
            "Languages: Python, Bash, Go, SQL",
            "Infrastructure: Docker, Terraform, AWS, CI/CD"
        ],
        "experience": [
            {
                "role": "Site Reliability Engineer",
                "company": "Apex Reliability Labs",
                "period": "2021 - Present",
                "bullets": [
                    "Formulated and tracked Service Level Objectives (SLOs) and Error Budgets for high-traffic payment APIs.",
                    "Wrote automated self-healing remediation scripts in Python and Bash for Kubernetes node failures.",
                    "Led incident post-mortems and minimized Mean Time to Recovery (MTTR) by 38%."
                ]
            },
            {
                "role": "Systems Administrator",
                "company": "Northwest Data Centers",
                "period": "2019 - 2021",
                "bullets": [
                    "Maintained fleet of 800+ Red Hat Linux servers and handled storage backup routines.",
                    "Automated patching and configuration management using Ansible."
                ]
            }
        ],
        "projects": [
            {"name": "AutoHealer Pod", "desc": "Kubernetes operator detecting memory leaks and recycling pods gracefully."},
            {"name": "SLO Dashboard Suite", "desc": "Grafana monitoring dashboards providing live latency and error budget tracking."}
        ],
        "education": "Bachelor of Science in Computer Information Systems, Oregon State (2019)"
    },
    {
        "filename": "Tariq_AlMansoor_Data_Engineer.pdf",
        "name": "Tariq Al-Mansoor",
        "title": "Senior Data Engineer",
        "email": "tariq.almansoor@example.com",
        "phone": "+1 (555) 456-0123",
        "location": "Houston, TX",
        "summary": "Senior Data Engineer with 6 years of experience architecting petabyte-scale data lakes and streaming ETL pipelines. Strong proficiency in SQL, Spark, Airflow, dbt, Snowflake, Python, and BigQuery.",
        "skills": [
            "Data Engineering: Spark, Hadoop, Airflow, dbt, Kafka, ETL",
            "Databases & Warehouses: Snowflake, BigQuery, PostgreSQL, MySQL, NoSQL",
            "Languages: Python, SQL, Scala",
            "Cloud & DevOps: AWS, GCP, Docker, Git"
        ],
        "experience": [
            {
                "role": "Lead Data Pipeline Engineer",
                "company": "DataStream Analytics",
                "period": "2021 - Present",
                "bullets": [
                    "Engineered daily ETL pipelines processing 4 TB of raw transactional events using Apache Spark and Airflow.",
                    "Designed star-schema data models in Snowflake and automated data quality transformations using dbt.",
                    "Reduced cloud query execution costs by 40% through partitioning and clustering in BigQuery."
                ]
            },
            {
                "role": "Data Engineer",
                "company": "Energy Analytics Corp",
                "period": "2018 - 2021",
                "bullets": [
                    "Developed Python ingestion scripts streaming IoT sensor telemetry into PostgreSQL data warehouses.",
                    "Wrote complex analytical SQL queries supporting business intelligence reporting."
                ]
            }
        ],
        "projects": [
            {"name": "StreamLake Ingestion", "desc": "Real-time streaming ingestion pipeline built using Kafka, Spark, and Snowflake."},
            {"name": "dbt Data Quality Framework", "desc": "Automated data verification test suite testing 500+ daily table models."}
        ],
        "education": "Master of Science in Information Systems, Texas A&M (2018)"
    },
    {
        "filename": "Jessica_Taylor_Cloud_Security.pdf",
        "name": "Jessica Taylor",
        "title": "Cloud Security Engineer",
        "email": "jessica.taylor@example.com",
        "phone": "+1 (555) 567-1234",
        "location": "Washington, DC",
        "summary": "Cloud Security Engineer with 4 years of experience implementing DevSecOps, identity governance, and vulnerability management. Skilled in AWS, Azure, Terraform, Linux, CI/CD, and security auditing.",
        "skills": [
            "Security: Cloud Security, Vulnerability Scanning, IAM, Cyber Security",
            "Platforms: AWS, Azure, Linux",
            "Automation: Terraform, Python, Bash, CI/CD, Git",
            "Compliance: SOC2, ISO 27001, CIS Benchmarks"
        ],
        "experience": [
            {
                "role": "Cloud Security Specialist",
                "company": "Fortress Cyber Defense",
                "period": "2022 - Present",
                "bullets": [
                    "Audited and remediated AWS IAM policies and security group rules across 30 enterprise accounts.",
                    "Integrated automated static code security scanners (SAST) into GitHub Actions CI/CD pipelines.",
                    "Authored Terraform guardrails enforcing encryption at rest and in transit for all cloud resources."
                ]
            },
            {
                "role": "Information Security Analyst",
                "company": "SecureNet Solutions",
                "period": "2020 - 2022",
                "bullets": [
                    "Conducted vulnerability assessments across Linux systems and performed incident response analysis.",
                    "Maintained compliance documentation for SOC2 and ISO 27001 security audits."
                ]
            }
        ],
        "projects": [
            {"name": "IAM Least Privilege Audit Tool", "desc": "Python utility detecting over-permissive AWS IAM credentials."},
            {"name": "Terraform Sentinel Guard", "desc": "Automated policy-as-code security check for infrastructure pull requests."}
        ],
        "education": "Bachelor of Science in Cybersecurity, George Mason University (2020)"
    },
    {
        "filename": "Rohan_Gupta_Data_Analyst_DBA.pdf",
        "name": "Rohan Gupta",
        "title": "Database Administrator & Data Analyst",
        "email": "rohan.gupta@example.com",
        "phone": "+1 (555) 678-2345",
        "location": "Phoenix, AZ",
        "summary": "Database Administrator and Analyst with 5 years of experience managing relational databases and delivering business intelligence. Expert in SQL, PostgreSQL, MySQL, Tableau, Power BI, Excel, and statistics.",
        "skills": [
            "Databases: PostgreSQL, MySQL, SQL Server, Redis, NoSQL",
            "Analytics & BI: Tableau, Power BI, Excel, Data Analysis, Statistics",
            "Languages & Scripts: SQL, Python, Bash",
            "DBA Skills: Index Optimization, Backup & Recovery, Performance Tuning"
        ],
        "experience": [
            {
                "role": "Senior Database Administrator",
                "company": "Apex Financial Services",
                "period": "2021 - Present",
                "bullets": [
                    "Managed 40+ PostgreSQL and MySQL production database clusters with automated replication and failover.",
                    "Optimized slow analytical SQL queries, improving batch execution times by up to 60%.",
                    "Configured disaster recovery backup routines ensuring zero data loss across business quarters."
                ]
            },
            {
                "role": "Business Data Analyst",
                "company": "Summit Retail Group",
                "period": "2019 - 2021",
                "bullets": [
                    "Engineered interactive sales and inventory dashboards in Tableau and Power BI.",
                    "Analyzed customer purchasing trends utilizing advanced SQL queries and Microsoft Excel."
                ]
            }
        ],
        "projects": [
            {"name": "DB Monitor Dashboard", "desc": "PostgreSQL health monitoring and slow query alert tool written in Python."},
            {"name": "Executive Sales BI Hub", "desc": "Enterprise Power BI dashboard integrating multi-store retail data."}
        ],
        "education": "Bachelor of Science in Management Information Systems, Arizona State (2019)"
    }
]


def create_resume_pdf(data: dict, out_path: Path):
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    name_style = ParagraphStyle(
        "ResumeName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1e293b"),
        alignment=0
    )

    title_style = ParagraphStyle(
        "ResumeTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#2563eb"),
    )

    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b")
    )

    section_style = ParagraphStyle(
        "ResumeSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155")
    )

    bold_body = ParagraphStyle(
        "ResumeBoldBody",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b")
    )

    bullet_style = ParagraphStyle(
        "ResumeBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#334155"),
        leftIndent=12,
        firstLineIndent=-8
    )

    story = []

    # 1. Header
    story.append(Paragraph(data["name"], name_style))
    story.append(Paragraph(data["title"], title_style))
    contact_line = f"{data['email']}  |  {data['phone']}  |  {data['location']}"
    story.append(Paragraph(contact_line, contact_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=6))

    # 2. Professional Summary
    story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
    story.append(Paragraph(data["summary"], body_style))
    story.append(Spacer(1, 4))

    # 3. Technical Skills
    story.append(Paragraph("TECHNICAL SKILLS", section_style))
    for skill in data["skills"]:
        story.append(Paragraph(f"• {skill}", bullet_style))
    story.append(Spacer(1, 4))

    # 4. Professional Experience
    story.append(Paragraph("WORK EXPERIENCE", section_style))
    for exp in data["experience"]:
        header_text = f"<b>{exp['role']}</b> — {exp['company']} ({exp['period']})"
        story.append(Paragraph(header_text, bold_body))
        for bullet in exp["bullets"]:
            story.append(Paragraph(f"• {bullet}", bullet_style))
        story.append(Spacer(1, 3))

    # 5. Key Projects
    if data.get("projects"):
        story.append(Paragraph("KEY PROJECTS", section_style))
        for proj in data["projects"]:
            story.append(Paragraph(f"<b>{proj['name']}</b>: {proj['desc']}", bullet_style))
        story.append(Spacer(1, 3))

    # 6. Education
    story.append(Paragraph("EDUCATION", section_style))
    story.append(Paragraph(data["education"], body_style))

    doc.build(story)
    print(f"Generated: {out_path.name}")


def main():
    print(f"Generating 15 test resumes in {OUTPUT_DIR}...")
    for item in RESUMES:
        out_file = OUTPUT_DIR / item["filename"]
        create_resume_pdf(item, out_file)
    print(f"Successfully generated all {len(RESUMES)} PDF resumes!")


if __name__ == "__main__":
    main()
