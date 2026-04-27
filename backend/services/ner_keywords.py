# ============================================================
# CONFIGURACIÓN CENTRAL DEL NER (EntityRuler)
# Versión optimizada con 5 categorías:
# AREAS, LENGUAJES, HERRAMIENTAS, METODOLOGIAS, CONTENIDOS
# ============================================================


# ============================================================
# 1. ÁREAS / DOMINIOS PROFESIONALES
# ============================================================

PATTERNS_AREAS = [
    'Machine Learning', 'Data Science', 'Inteligencia Artificial', 'AI',
    'Desarrollo Mobile', 'Android', 'iOS', 'React Native',
    'Backend', 'Frontend', 'Full Stack', 'DevOps',
    'Cloud Computing', 'AWS', 'Azure', 'GCP',
    'Blockchain', 'Ciberseguridad', 'Seguridad Informática',
    'IoT', 'Robótica', 'Redes', 'Sistemas',
    'Base de Datos', 'BI', 'Business Intelligence', 'Analytics', 'Analítica',
    'UX/UI', 'HCI', 'Interacción Humano-Computadora',
    'Ingeniería de Software', 'Calidad de Software', 'QA',
    'Big Data', 'Procesamiento de Lenguaje Natural', 'PLN', 'NLP',
    'Sistemas de Información', 'Gestión de Proyectos de TI',
    'Computación Visual', 'Visión Artificial',
    'Telecomunicaciones',
    'Sistemas Operativos',
    'Arquitectura y Administración de Redes',
    'Auditoría de Sistemas',
    'Desarrollo de Aplicaciones Móviles',
    'Realidad Aumentada',
    'Web Semántica',
    'Redes Neuronales',
    'Sistemas Inteligentes',
    'Ingeniería Web', 'Aplicaciones Web',
    'Ciencias de la Computación',
    'Ingeniería de Datos',
    'Minería de Datos', 'Educational Data Mining',
    'Gamificación',
    'Gestión de Infraestructura TI',
    'DBA',
    'Software Empresarial',
    'Grid Computing',
    'Sistemas de Información Organizacional',
    'Ingeniería Empresarial',
    'Simulación de Sistemas',
    'Sector Gobierno', 'Banca', 'Seguros', 'Educación',
    'Tecnologías Educativas', 'E-learning',
    'Smart City', 'Ciudades Inteligentes',
    'Algoritmos Genéticos',
    'Gobierno y Gestión de TI',
    'Gestión de Servicios de TI',
    'Procesos de Negocio',
    'Sistemas de Información Gerencial',
    'Auditoría y Gestión de Procesos',
    'Herramientas TIC', 'TIC',
    'Reingeniería de Procesos'
]


# ============================================================
# 2. LENGUAJES DE PROGRAMACIÓN
# ============================================================

PATTERNS_LENGUAJES = [
    'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'C',
    'PHP', 'Ruby', 'Go', 'Rust', 'Swift', 'Kotlin', 'R', 'MATLAB',
    'Scala', 'Perl', 'Shell', 'Bash', 'SQL', 'HTML', 'CSS',
    'PL/SQL',
    'Shell Scripting', 'Lenguaje Ensamblador',
    'AJAX',
    'Archimate',
    'CSS3',
    'expresiones regulares',
    'HTML5',
    'IOS (Cisco)',
    'MySQL (lenguaje)',
    'Prolog',
    'shell de Linux',
    'Shell scripts',
    'Solidity'
]


# ============================================================
# 3. HERRAMIENTAS, FRAMEWORKS, LIBRERÍAS, PLATAFORMAS
# ============================================================

PATTERNS_HERRAMIENTAS = [
    'React', 'Angular', 'Vue.js', 'Node.js', 'Express', 'Django', 'Flask',
    'Spring', 'Laravel',
    'TensorFlow', 'PyTorch', 'Keras', 'Scikit-learn',
    'Docker', 'Kubernetes', 'Jenkins',
    'Git', 'GitHub', 'GitLab',
    'MongoDB', 'PostgreSQL', 'MySQL', 'Redis', 'Elasticsearch',
    'Tableau', 'Power BI',
    'Jupyter', 'VS Code', 'IntelliJ',
    'Jira', 'Trello', 'Slack', 'Figma', 'Adobe XD',
    'Firebase', 'Heroku',
    'Spark', 'Hadoop', 'Pandas', 'NumPy',
    'Amazon Web Services', 'Microsoft Azure', 'Google Cloud Platform',
    'ERP Banner', 'Banner', 'Ellucian',
    'Pentaho', 'QlikSense', 'MicroStrategy',
    'GNU/Linux', 'Linux',
    'Turnitin',
    'Canvas', 'LMS Canvas', 'LMS Moodle', 'Moodle',
    'Zoom',
    'Word', 'PowerPoint', 'Excel', 'Access',
    'Microsoft Office', 'Google Workspace',
    'SQL Server',
    'RPA', 'RPAS',
    'Terraform',
    'SpringBoot',
    'SAP',
    'Looker Studio',
    'ATLAS.ti',
    'Oracle SQL Developer', 'Oracle',
    'RMAN',
    'AIX',
    'Visual Studio',
    'Notion', 'Lucidchart', 'Cmaptools', 'GoConqr',
    'Packet Tracer',
    'Windows Server',
    'Android Studio',
    'Arduino',
    'Bootstrap',
    'CentOS', 'Debian', 'Kali Linux',
    'Nmap', 'Node-RED',
    'OpenSSL',
    'Oracle VM VirtualBox',
    'Orange (data mining software)',
    'RecyclerView',
    'ScienceDirect', 'SCOPUS', 'IEEE Xplore',
    'SIEM', 'Snort',
    'SPSS',
    'Truffle',
    'Unreal Engine',
    'Web3.js',
    'Wireshark',
    'Wordpress REST API',
    'UXPin'
]


# ============================================================
# 4. METODOLOGÍAS, ESTÁNDARES, MARCOS, CERTIFICACIONES
# ============================================================

PATTERNS_METODOLOGIAS = [
    'Scrum', 'Kanban', 'Agile', 'XP', 'Extreme Programming', 'Lean',
    'RUP', 'Design Thinking', 'TDD', 'BDD',
    'DevSecOps',
    'PMBOK', 'ITIL', 'ITIL 4', 'ITIL 3',
    'ISO 9001', 'ISO 9001:2015', 'ISO 31000', 'ISO 27001', 'ISO 27002',
    'CMMI',
    'BPMN',
    'TOGAF',
    'COBIT', 'COBIT 2019',
    'UML',
    'SWEBOK',
    'ISO 29110',
    'INCOSE',
    'SOLID',
    'User Stories',
    'Heurísticas', 'Usabilidad', 'Accesibilidad',
    'Impact Map',
    'Metodologías Ágiles',
    'CCNA',
    'Aprendizaje Basado en Problemas',
    'Aprendizaje Basado en Proyectos',
    'Aula invertida',
    'Domain Driven Design',
    'Lean Startup',
    'Matriz RACI',
    'Modelo MVC',
    'Normas APA',
    'Pareto',
    'PMV (producto mínimo viable)',
    'Programación en Parejas',
    'RAD (Rapid Application Development)',
    'SPICE',
    'Teoría de las Restricciones'
]


# ============================================================
# 5. CONTENIDOS (TEMAS DE CURSOS, CONCEPTOS, TEORÍA)
# ============================================================

PATTERNS_CONTENIDOS = [
    # Algoritmia, Estructuras de Datos
    'fundamentos de programación', 'programación estructurada',
    'grafos', 'grafos dirigidos',
    'árboles', 'árboles binarios',
    'Estructura de Datos', 'Estructuras de Datos', 'Algoritmos', 'Algoritmia',
    'Máquinas de estado finito', 'Autómatas',
    'Lenguajes regulares', 'Conjuntos parcialmente ordenados',
    'Complejidad Algorítmica', 'Notación Big O', 'Ordenamiento', 'Búsqueda',

    # Matemáticas
    'Matemática Discreta',
    'cálculo diferencial', 'cálculo integral',
    'Funciones reales', 'Límites', 'derivada',
    'Álgebra Lineal', 'Geometría Descriptiva',
    'ecuaciones diferenciales',
    'probabilidades', 'teorema de Bayes', 'distribución de probabilidades',
    'estadística descriptiva', 'regresión lineal',

    # Redes y SO
    'Direccionamiento IP', 'Protocolos y puertos',
    'TCP', 'UDP', 'DNS', 'DHCP', 'Subnetting', 'VLSM',
    'Capa física', 'Capa de red', 'Capa de transporte', 'Capa de aplicación',

    # Bases de Datos
    'Modelo E-R', 'Modelo Relacional', 'normalización',
    'algebra relacional', 'transacciones',

    # Investigación
    'investigación científica', 'investigación aplicada',
    'métodos de investigación', 'monografía',
    'planteamiento del problema', 'recolección de datos',
    'análisis cualitativo', 'análisis cuantitativo',

    # Ingeniería de Software
    'Requisitos funcionales', 'Requisitos no funcionales',
    'Diagrama de clases', 'casos de uso',
    'modelado AS-IS', 'modelado TO-BE',
    'validación y verificación de software',

    # Seguridad
    'ethical hacking',
    'análisis de vulnerabilidades',
    'amenazas',
    'cifrado',

    # Otros contenidos relevantes
    'Procesamiento digital de imágenes',
    'Reconocimiento de Patrones',
    'Simulación de procesos',
    'ETL',
    'OLAP', 'OLTP',
    'modelamiento multidimensional',
    'Smart Contracts',
    'Transformación digital'
]
