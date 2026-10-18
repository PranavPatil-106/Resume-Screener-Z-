export interface JobDescription {
  id: string
  title: string
  category: string
  description: string
  tags: string[]
  experience: string
  employmentType: string
  activeScreenings: number
  updatedAt: string
}

export const SAMPLE_JDS: JobDescription[] = [
  {
    id: 'jd-01',
    title: 'AI Engineer',
    category: 'AI & Data',
    description: 'Specializes in LLM integrations, fine-tuning, RAG pipelines, and deploying performant vector-search architectures.',
    tags: ['Python', 'PyTorch', 'LLMs & RAG', 'LangChain', 'Vector DBs'],
    experience: '3+ years',
    employmentType: 'Full-time',
    activeScreenings: 2,
    updatedAt: 'Updated 2 days ago',
  },
  {
    id: 'jd-02',
    title: 'Backend Developer',
    category: 'Engineering',
    description: 'Designs reliable RESTful and asynchronous backend services, database schemas, and microservice pipelines.',
    tags: ['Python / FastAPI', 'PostgreSQL', 'Redis', 'Docker', 'System Design'],
    experience: '4+ years',
    employmentType: 'Full-time',
    activeScreenings: 1,
    updatedAt: 'Updated 4 days ago',
  },
  {
    id: 'jd-03',
    title: 'Data Scientist',
    category: 'AI & Data',
    description: 'Applies statistical modeling, exploratory data analysis, and predictive machine learning algorithms to core product problems.',
    tags: ['Python', 'Pandas / NumPy', 'Scikit-Learn', 'Statistics', 'SQL'],
    experience: '3+ years',
    employmentType: 'Full-time',
    activeScreenings: 1,
    updatedAt: 'Updated 1 week ago',
  },
  {
    id: 'jd-04',
    title: 'Full Stack Developer',
    category: 'Engineering',
    description: 'Delivers customer-facing web applications with modern frontend frameworks and clean, secure backend APIs.',
    tags: ['React', 'TypeScript', 'Node.js / Python', 'REST APIs', 'CSS3'],
    experience: '2+ years',
    employmentType: 'Full-time',
    activeScreenings: 1,
    updatedAt: 'Updated 1 week ago',
  },
]

export interface ScreeningSession {
  id: string
  role: string
  department: string
  resumesCount: number
  shortlistedCount: number
  avgScore: number
  status: 'Completed' | 'In Progress' | 'Queued'
  date: string
}

export const SAMPLE_SESSIONS: ScreeningSession[] = [
  {
    id: 'sess-01',
    role: 'Senior Full-Stack Engineer',
    department: 'Engineering',
    resumesCount: 64,
    shortlistedCount: 9,
    avgScore: 94,
    status: 'Completed',
    date: 'Oct 05, 2026',
  },
  {
    id: 'sess-02',
    role: 'Lead Product Designer',
    department: 'Design & UX',
    resumesCount: 42,
    shortlistedCount: 6,
    avgScore: 89,
    status: 'In Progress',
    date: 'Oct 04, 2026',
  },
  {
    id: 'sess-03',
    role: 'Backend Python Architect',
    department: 'Platform Engineering',
    resumesCount: 58,
    shortlistedCount: 8,
    avgScore: 91,
    status: 'Completed',
    date: 'Oct 02, 2026',
  },
  {
    id: 'sess-04',
    role: 'Data Platform Engineer',
    department: 'AI & Data Systems',
    resumesCount: 35,
    shortlistedCount: 5,
    avgScore: 86,
    status: 'In Progress',
    date: 'Sep 30, 2026',
  },
  {
    id: 'sess-05',
    role: 'Technical Product Manager',
    department: 'Product Management',
    resumesCount: 49,
    shortlistedCount: 8,
    avgScore: 92,
    status: 'Completed',
    date: 'Sep 28, 2026',
  },
]

export interface CandidateProfile {
  id: string
  name: string
  headline: string
  score: number
  tier: 'Strong Match' | 'Good Match' | 'Partial Match' | 'Low Match'
  experience: string
  skills: string[]
  education: string
}

export const SAMPLE_CANDIDATES: CandidateProfile[] = [
  {
    id: 'cand-01',
    name: 'Rahul Kumar',
    headline: 'Senior Full-Stack Engineer • ex-Fintech',
    score: 94,
    tier: 'Strong Match',
    experience: '6 years',
    skills: ['React', 'TypeScript', 'Node.js', 'PostgreSQL', 'Docker'],
    education: 'B.Tech Computer Science',
  },
  {
    id: 'cand-02',
    name: 'Priya Singh',
    headline: 'Full-Stack Developer • Cloud Platforms',
    score: 89,
    tier: 'Good Match',
    experience: '5 years',
    skills: ['Python', 'FastAPI', 'React', 'Redis', 'AWS'],
    education: 'M.S. Software Engineering',
  },
  {
    id: 'cand-03',
    name: 'Amit Patel',
    headline: 'Senior Software Engineer • Distributed Apps',
    score: 82,
    tier: 'Good Match',
    experience: '4.5 years',
    skills: ['TypeScript', 'Vue.js', 'Django', 'GraphQL', 'Postgres'],
    education: 'B.E. Information Technology',
  },
  {
    id: 'cand-04',
    name: 'Sneha Reddy',
    headline: 'Backend & Web Developer • Microservices',
    score: 68,
    tier: 'Partial Match',
    experience: '3 years',
    skills: ['JavaScript', 'Node.js', 'Express', 'MongoDB', 'REST APIs'],
    education: 'B.Tech Information Science',
  },
  {
    id: 'cand-05',
    name: 'Vikram Jain',
    headline: 'Web Application Developer • CMS & Systems',
    score: 52,
    tier: 'Low Match',
    experience: '2 years',
    skills: ['PHP', 'Laravel', 'MySQL', 'jQuery', 'HTML5/CSS3'],
    education: 'B.Sc. Computer Science',
  },
]

export type UserRole = 'Admin' | 'Recruiter' | 'Viewer'
export type UserStatus = 'Active' | 'Pending Invite' | 'Inactive'

export interface UserRecord {
  id: string
  name: string
  email: string
  role: UserRole
  status: UserStatus
  department: string
  lastActive: string
}

export const SAMPLE_USERS: UserRecord[] = [
  {
    id: 'user-01',
    name: 'Sarah Parker',
    email: 'sarah.parker@example.com',
    role: 'Recruiter',
    status: 'Active',
    department: 'Talent Acquisition',
    lastActive: 'Just now',
  },
  {
    id: 'user-02',
    name: 'Alex Rivera',
    email: 'alex.rivera@example.com',
    role: 'Admin',
    status: 'Active',
    department: 'People Operations',
    lastActive: '2 hours ago',
  },
  {
    id: 'user-03',
    name: 'David Chen',
    email: 'david.chen@example.com',
    role: 'Recruiter',
    status: 'Active',
    department: 'Technical Hiring',
    lastActive: 'Yesterday',
  },
  {
    id: 'user-04',
    name: 'Maya Patel',
    email: 'maya.patel@example.com',
    role: 'Viewer',
    status: 'Active',
    department: 'Engineering Leadership',
    lastActive: 'Oct 04, 2026',
  },
  {
    id: 'user-05',
    name: 'Elena Rostov',
    email: 'elena.rostov@example.com',
    role: 'Viewer',
    status: 'Pending Invite',
    department: 'Operations & Strategy',
    lastActive: 'Invited 3 days ago',
  },
]
