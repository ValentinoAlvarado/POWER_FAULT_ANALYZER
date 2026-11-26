# POWER_FAULT_ANALYZER — Auditoría técnica de capacidades

**Fecha:** 2026-11-24
**Base documental:** `POWER_FAULT_ANALYZER_CONSOLIDATED_SOURCE_20261123.zip` (snapshot consolidado disponible en el entorno de auditoría).
**Estado local declarado por Windows:** rama `product-reboot`, HEAD `2ce715c6e38df24f9348ed327d3cb81d04349497`, árbol limpio.
**Limitación de identidad:** el ZIP disponible no contiene `.git` y precede al último commit local reportado (`2ce715c`). Ese commit fue descrito en el log del propietario como formato exclusivamente equivalente a nivel AST para `scripts/smoke_test_app_reboot_005.py`; esta auditoría no afirma equivalencia byte a byte con HEAD ni inspección directa de su objeto Git.

## 1. Dictamen ejecutivo

El repositorio ya contiene un motor de cortocircuito por componentes simétricas, una capa de modelos eléctricos, puertos y adaptadores, persistencia JSON, exportación de informes y un Workbench PySide6 con un editor gráfico. No es un proyecto vacío ni una simple interfaz.

Tampoco es todavía una plataforma integral de ingeniería. Las desconexiones de mayor impacto son:

1. La entidad `Bus` representa tanto barras como nodos internos mediante `BusKind`; el modelo de conectividad no tiene aún una entidad independiente `ConnectivityNode`/`TerminalConnectivity` ni una semántica completa de equipos multi-terminales.
2. La UI permite crear desde su paleta un subconjunto de equipos, pero no todos los modelos existentes tienen flujo completo de inserción, parametrización, conexión, persistencia y estudio.
3. La colocación gráfica y la topología están separadas, pero la edición general de conexiones por terminales y la sincronización de múltiples diagramas todavía no conforman un editor de red completo.
4. No se encontró un caso de uso de flujo de carga AC/DC, análisis N-1/N-k, OPF, despacho económico ni programación hidro-térmica. La presencia de Ybus no equivale a esos estudios.
5. ND-016 y el adaptador externo existen; el informe analítico interno y la sensibilidad cubren un dominio limitado. La comparación con PowerWorld no debe presentarse como un expediente de referencia externa completo ni como cierre de todas las fallas.
6. La simbología QET conserva procedencia y licencia, pero los 18 activos del manifiesto se declaran `candidate`, no símbolos IEC 60617 cuya edición/identidad se haya verificado.
7. No se encontraron importadores completos CIM/CGMES, PSS/E RAW/DYR, MATPOWER, COMTRADE ni una API FastAPI implementada. `interfaces/api` contiene únicamente su inicializador.
8. La licencia raíz del producto está vacía; la publicación binaria está bloqueada por el propio `build_windows_release.ps1`. No hay evidencia adjunta de un ZIP portable probado en Windows limpio.

## 2. Matriz de capacidades

| Dominio auditado | Clasificación | Código y flujo observado | Pruebas/evidencia observada | Brecha principal |
|---|---|---|---|---|
| Modelo eléctrico y topología | IMPLEMENTADO PARCIALMENTE | `domain/aggregates/network.py` registra buses, equipos, terminales y `Connection`; `domain/entities/bus.py`; `domain/entities/terminal.py`; `domain/value_objects/connection.py`; `network/sequence_networks/builder.py`; `network/topology.py` | Pruebas unitarias de dominio, topología y construcción de redes de secuencia | `BusKind` diferencia `BUSBAR`/`CONNECTION_NODE`, pero ambos siguen almacenados como `Bus`. Falta modelo de nodos/conectividad independiente, busbar sections, terminales de equipo multi-terminal y switch states completos para toda la topología. |
| Equipos, terminales y conexiones | IMPLEMENTADO PARCIALMENTE | `equipment/transmission/`, `equipment/transformers/`, `equipment/sources/`, `equipment/motors/`, `equipment/converters/`, `equipment/switching/`; contratos en `domain/interfaces/network_contracts.py` | Pruebas de modelos de equipos, transformadores, fuentes, conectividad y secuencias | El directorio `equipment/loads/` no contiene modelo de carga. La UI no crea todos los equipos de dominio. PFA-ES-001 añade switchgear y dos interfaces externas aún no parametrizadas. |
| Proyectos y persistencia | IMPLEMENTADO PARCIALMENTE | `application/use_cases/project_workspace.py`; `infrastructure/persistence/json_project_repository.py`; `application/use_cases/network_workspace.py`; `infrastructure/persistence/json_network_document_repository.py` | Pruebas de ciclo de proyecto, migración/round-trip de documentos y ahora schema `1.2` | Proyecto y red se guardan en JSON `.pfa` + sidecar. No hay gestión completa de revisiones, variantes, transacciones multiusuario, recuperación/autosave versionado ni almacenamiento de múltiples hojas. El writer de red sigue necesitando soporte explícito por cada clase de equipo. |
| Editor gráfico y equipos de dominio | IMPLEMENTADO PARCIALMENTE | `interfaces/desktop/workbench/network_canvas.py` (`BusSymbol`, `SourceSymbol`, `BranchSymbol`, `NetworkCanvasView`); `qet_symbol_item.py`; `qet_symbol_browser.py`; `workbench_window.py`; composición en `bootstrap/workbench_container.py` | Pruebas de APP-005 históricas; pruebas de workspace/undo; smoke nuevo PFA-ES-001 pendiente de Windows | Paleta base de creación: BUS, fuente Thévenin, generador síncrono y línea. No hay edición arbitraria de terminales/conexiones, multihoja completa, edición tabular, layout automático ni ruteo ortogonal integrado. El inspector es mayormente de solo lectura; en PFA-ES-001 se edita el estado de interruptores. |
| Biblioteca de símbolos y procedencia | IMPLEMENTADO PARCIALMENTE | `infrastructure/symbols/qet_catalog.py`, `qet_elmt.py`; `RESEARCH/qelectrotech-symbol-candidates.csv`; `assets/third_party/qelectrotech-elements/` | Pruebas de manifiesto, SHA/blob de origen y renderizador/importador QET | 18 activos con `normative_status=candidate`; no se dispone de verificación individual frente a IEC 60617 DB/edición y contexto de uso. La colección declara CC BY 3.0 al redistribuir activos fuera de diagramas; prohíbe usar esos ficheros como datos de muestra para entrenar modelos ML. |
| Motor numérico y solvers | IMPLEMENTADO Y VALIDADO EN DOMINIOS ACOTADOS | `solvers/fault_solver.py`, `sparse_solver.py`, `thevenin.py`; `infrastructure/numerical/short_circuit.py`, `line_fault.py`, `ybus.py`, `iec60909.py`, `short_circuit_waveform.py`, `source_contributions.py`; `standards/iec60909/` | Pruebas unitarias/integración en `tests/unit/network`, `tests/unit/standards`, `tests/unit/equipment`, etc. | El cálculo de fallas académicas por secuencias está implementado. IEC 60909 está parcialmente modelada; no se declara cumplimiento total IEC 60909-0:2026. No se identificó solver de flujo de carga Newton-Raphson, DC load flow ni OPF. Ybus es infraestructura matricial, no un flujo de estudio por sí solo. |
| Estudios, escenarios y validación | IMPLEMENTADO PARCIALMENTE | `application/use_cases/run_network_short_circuit_study.py`; `validation/benchmark_runner.py`, `reference_cases.py`, `electrical_checks.py`, `sensitivity.py`, `external_reference.py`, `cli.py` | Log histórico ND-016: 4/4 casos analíticos, 44/44 cantidades, 4/4 auditorías, sensibilidad con diferencia relativa `4.481e-07`; un caso PowerWorld descrito 6/6 por transcripción de tablas | No hay gestor completo de Study Cases/variantes ni ejecución de contingencias. Comparación PowerWorld nativa PWB/CSV/Message Log completa y casos A-G, LL y DLG permanecen pendientes según la continuidad disponible. |
| Resultados, gráficos e informes | IMPLEMENTADO PARCIALMENTE | `results/result_models.py`, `results/report_builder.py`; `reporting/pdf_exporter.py`, `excel_exporter.py`, `csv_exporter.py`, `json_exporter.py`; `interfaces/desktop/workbench/results_workspace.py` | Pruebas de modelos/resultados, generación y exportación; aceptación GUI APP-005 histórica | El builder solo puede reportar cantidades que entrega el solver. No se reconstruyen corrientes de todas las ramas si no están disponibles. Falta comparación entre escenarios, resultados de flujo de carga y contingencias. |
| Importación/exportación | IMPLEMENTADO PARCIALMENTE | Importador QET; `validation/external_reference.py` acepta JSON schema `1.0.0`; exportadores de informes; `JSONNetworkDocumentRepository` | Pruebas de importador QET, esquema de referencia externa, round-trip JSON y exportadores | No se encontraron importadores completos CIM/CGMES, PSS/E RAW/DYR, MATPOWER, PowerWorld PWB/AUX/CSV, COMTRADE ni IEC 61850 SCL. Abrir JSON o un símbolo QET no prueba fidelidad de importación de modelos eléctricos externos. |
| Arquitectura, rendimiento y escalabilidad | IMPLEMENTADO PARCIALMENTE | `domain/`, `application/`, `infrastructure/`, `interfaces/`, `bootstrap/`; puertos en `application/ports/`; adaptadores en `infrastructure/adapters/` | Pruebas de contratos, dominio, aplicación e integración de escritorio | DDD + ports/adapters es reconocible. Todavía existen carpetas de transición/legacy y no se encontraron benchmarks sistemáticos de carga, layout, memoria o solver en redes de 100/300/1 000+ barras. La UI depende de Qt Graphics View sin virtualización probada a escala. |
| Distribución, dependencias y cadena de suministro | PREPARADO PARCIALMENTE / BLOQUEADO | `pyproject.toml`; `scripts/build_windows_release.ps1`; `.github/workflows/windows-release.yml`; `website/index.html`, `release.js`, `styles.css` | Build script y workflows presentes en snapshot | `LICENSE` raíz tiene 0 bytes; el build aborta. Sitio mantiene `YOUR_GITHUB_OWNER/POWER_FAULT_ANALYZER`. No se observó lockfile/SBOM ni evidencia de instalación limpia. Workflows usan tags de acciones y permisos amplios `contents: write`; endurecer pinning SHA, permisos por job, retención y procedencia antes del release. |
| IA de ingeniería y trazabilidad de fuentes | NO IMPLEMENTADO | No se encontraron casos de uso/adapter/assistant que conecten extracción de documentos con cambios al modelo de red | No se encontraron pruebas de extracción asistida/validación humana | Es un requisito V3/V4 futuro. Se requiere pipeline con extracción, provenance ledger, review/approval y validadores deterministas; no incorporar aún como chatbot decorativo. |
| Dominios industriales integrados | NO IMPLEMENTADO COMO FLUJOS DE PRODUCTO | Existen áreas de dominio para equipos de potencia, motores, convertidores y protección | Pruebas aisladas de modelos | No hay producto integrado para instalaciones/tableros/cables/borneras, PLC/IED/RTU/SCADA analítico, instrumentación/P&ID, electrónica/firmware/comunicaciones industriales ni gestión de documentación multi-disciplina. |

## 3. Arquitectura observada y flujo de datos

```text
PySide6 Workbench
    └── WorkbenchWindow / NetworkCanvasView / QETSymbolItem
          └── WorkbenchApplicationServices (bootstrap/workbench_container.py)
                ├── Application use cases
                │     ├── ProjectWorkspaceService
                │     ├── Network editing use cases
                │     ├── RunNetworkShortCircuitStudy
                │     └── ExportStudyReport
                ├── Domain Network aggregate
                │     ├── Bus / terminals / explicit connections
                │     └── equipment models
                └── Infrastructure adapters
                      ├── JSON repositories
                      ├── sequence network factory
                      ├── sparse short-circuit solver
                      └── report exporters
```

La topología vive en `Network`; la ubicación del dibujo vive en `NetworkWorkspace.diagram_positions` y `diagram_symbols`. En los símbolos nuevos, `equipment_id` y `terminal_mappings` enlazan un pin gráfico de origen a un terminal real del equipo. La validación exige que el terminal pertenezca al equipo y tenga una conexión explícita en el agregado. Esto evita inferir conectividad por cruce visual.

La frontera entre dominio e infraestructura no es perfecta todavía: `Bus` tiene un `BusKind` como distinción semántica en vez de una entidad independiente para `ConnectivityNode`; se debe migrar con contratos compatibles antes de abrir modelado IEC CIM de granularidad completa.

## 4. Auditoría de validación eléctrica

- El comando `pfa-validate` apunta a `power_fault_analyzer.validation.cli:main`.
- `validation/cli.py` ejecuta el benchmark analítico incorporado, auditorías eléctricas, sensibilidad y comparación externa opcional.
- La comparación externa requiere JSON schema `1.0.0` con `tool_name`, `tool_version`, `reference_dataset_id`, `case_id` y magnitudes/unidades admitidas por `validation/external_reference.py`.
- La ruta principal de la suite de validación usa una solución dispersa directa; por eso el informe marca convergencia iterativa como no aplicable. Esto no sustituye estrés de tamaño, estabilidad numérica ni benchmark de rendimiento.
- El estudio genérico `RunNetworkShortCircuitStudy` indica expresamente en el informe que no aplica correcciones IEC 60909. No mezclar ambas rutas.
- La comparación PowerWorld de REF-3PH-001B 6/6 indicada por el historial se basa en valores transcritos de tablas. Hasta conservar el proyecto nativo, exportaciones de alta precisión y Message Log, describirla como comparación numérica externa acotada, no como expediente documental reproducible completo.

## 5. Dependencias y disposición tecnológica

| Herramienta | Rol potencial | Decisión para PFA | Observaciones de integración/licencia |
|---|---|---|---|
| Eclipse Layout Kernel (ELK) / elkjs | Auto-layout jerárquico y por capas; puertos explícitos y ruteo de edges | EVALUAR EN PROTOTIPO, NO AÑADIR COMO DEPENDENCIA TODAVÍA | ELK calcula posiciones/dimensiones; no sustituye el canvas Qt. La capa Java/JS implica puente/proceso/empacado. ELK 0.12.1 fue publicado el 2026-10-28; revisar EPL-2.0 y opción secundaria declarada en el artefacto concreto antes de redistribuir. |
| Graphviz | Layout de grafos y exportación estática para informes/documentación | RESERVAR PARA EXPORTACIÓN/ANÁLISIS ESTÁTICO | No es sustituto de ruteo incremental de un editor interactivo con puertos y terminales. La página oficial declara EPL-2.0 para las versiones actuales; revisar la versión exacta empaquetada. |
| libavoid | Ruteo incremental ortogonal/polyline evitando obstáculos | CANDIDATO PARA FASE POSTERIOR DE ROUTING | C++ y binding nativo; no tiene releases oficiales según el sitio del proyecto. El código muestra LGPL-2.1-or-later y disponibilidad de licencia comercial. Añade deuda de ABI/compilación/packaging Windows. |

Fuentes consultadas el 2026-11-24:
- ELK: https://eclipse.dev/elk/ ; https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html ; https://projects.eclipse.org/projects/modeling.elk/releases/0.12.1 ; https://github.com/eclipse-elk/elk
- Graphviz: https://graphviz.org/license/ ; https://graphviz.org/
- libavoid: https://www.adaptagrams.org/documentation/libavoid.html ; https://github.com/mjwybrow/adaptagrams/blob/master/cola/libavoid/README

## 6. Evaluación de motores eléctricos externos (sin integración automática)

La arquitectura correcta no es importar un framework completo dentro del dominio. PFA conserva su modelo, sus unidades, sus identificadores, sus reglas de validación y sus resultados normalizados. Cada herramienta externa se conecta mediante un adapter y una declaración explícita de capacidades; los datos que no puedan mapearse deben producir warnings y un reporte de pérdidas. Los algoritmos PFA existentes de cortocircuito no se sustituyen por defecto.

| Proyecto | Capacidades relevantes documentadas | Licencia reportada | Papel recomendado | Riesgos y condición previa |
|---|---|---|---|---|
| pandapower | Power flow, cortocircuito, OPF, análisis N-1/contingency y state estimation; elementos de líneas, transformadores, motores, switches, storage, shunts y VSC aparecen en la documentación | BSD 3-Clause | PRIMER ADAPTER A EVALUAR para AC power flow, diagnóstico y benchmark cruzado; más adelante contingency analysis | Igualar modelos, bases, tap/phase-shift, earth/zero-sequence y límites antes de comparar. El modelo interno PFA debe conservar la fuente de verdad. Verificar versión y dependencias concretas antes de fijar. |
| PyPSA | Economic dispatch, unit commitment, almacenamiento intertemporal, hidro, LOPF lineal y security-constrained LOPF; modelos de energía multi-periodo | MIT | ADAPTER PARA planificación/optimización energética y BESS/hidro/renovables | La formulación documentada de OPF es linealizada; no presentarla como AC nonlinear OPF. Validar supuestos de pérdidas, KVL/KCL, snapshots, unidad y datos de coste. Revisar solver LP/MILP y sus propias licencias. |
| ANDES | AC power flow, dinámica RMS/time-domain, estabilidad transitoria, eigenvalue/small-signal, modelos de máquinas/controladores y renovables; parseo PSS/E RAW/DYR | GPL-3.0-or-later | CANDIDATO PARA dinámica y estabilidad como motor externo opcional | Licencia GPLv3 requiere evaluación específica antes de integrar/enlazar y distribuir con PFA. Preferir inicialmente un adapter a herramienta instalada separadamente y revisión legal; no empaquetar automáticamente. |
| GridCal | Plataforma de análisis con solver de flujo de carga, cortocircuito, optimización y GUI; admite MATPOWER y varios formatos en releases documentadas | MPL-2.0 en el paquete GridCal 5.4.1 consultado en PyPI | REFERENCIA DE PRODUCTO y candidato de adapter/interoperabilidad | Auditar versión/tag y el conjunto de ficheros de terceros; sus componentes pueden tener licencias adicionales. No integrar su GUI ni copiar código sin análisis de APIs, fidelidad de modelo y rendimiento. |

Fuentes consultadas el 2026-11-24:
- pandapower: https://pandapower.readthedocs.io/en/stable/ ; https://pandapower.readthedocs.io/en/stable/contingency.html ; https://www.pandapower.org/about/
- PyPSA: https://docs.pypsa.org/latest/ ; https://docs.pypsa.org/latest/user-guide/optimization/overview/
- ANDES: https://docs.andes.app/en/stable/ ; https://docs.andes.app/en/stable/about.html
- GridCal: https://github.com/claysiusd/GridCal ; https://pypi.org/project/GridCal/

## 7. Riesgos críticos y orden de resolución

| Severidad | Riesgo | Acción exigida |
|---|---|---|
| CRÍTICO | Busbar y ConnectivityNode no son entidades separadas | Introducir un modelo de conectividad explícito por nodos/terminales; migración JSON compatible y tests de equivalencia topológica. |
| CRÍTICO | Integración de modelos de equipos incompleta | Un catálogo con `EquipmentCapability` por equipo: UI, terminales, parámetros, persistencia, solvers/estudios soportados y evidencia. No habilitar inserción de un equipo si el flujo posterior no existe. |
| CRÍTICO | Falta AC/DC load flow y contingencias como estudios | Diseñar port de solver y comparar primero pandapower/PyPSA/ANDES según cada función, sin duplicar el motor ya validado ni mezclar resultados IEC. |
| ALTO | Símbolos candidatos no acreditados normativamente | Matriz de trazabilidad por símbolo, edición, terminales y licencia; bloquear claims IEC 60617. |
| ALTO | Falta importación de formatos de ingeniería | Diseñar un pipeline de importación con reportes de pérdidas, conversiones de base, objetos omitidos y provenance. |
| ALTO | Persistencia multihoja/revisiones ausente | Esquema de documento de proyecto con varias vistas y revisiones, migraciones explícitas y recuperación. |
| ALTO | Cero benchmarks grandes | Agregar datasets reproducibles 10/100/300/1 000 nodos y medir CPU, RAM, canvas, ruteo y solver. |
| ALTO | Licencia raíz vacía + cadena de suministro incompleta | Decisión del propietario para licencia PFA; revisar Qt/PySide6, assets QET, notices, lock, SBOM y workflows. |
| MEDIO | Ausencia de asistente IA de ingeniería | Diseñar ingestión determinista primero; las propuestas IA requieren provenance, conflictos y aprobación antes de cambiar modelo. |

## 8. PFA-ES-001 — alcance implementado en este incremento

El incremento crea una subestación estructural 220 kV de doble barra con dos posiciones: línea y transformador. Por cada posición se crean cuatro dispositivos de maniobra: seccionador de barra 1, seccionador de barra 2 (normalmente abierto), interruptor y seccionador lado equipo. Cada dispositivo es un objeto `SwitchingDevice` con dos terminales y una posición explícita. Las conexiones de terminales al modelo son explícitas; los dispositivos cerrados se proyectan como fusión topológica ideal, sin introducir impedancia ficticia.

Los extremos remotos de la línea y del transformador son `UnresolvedEquipmentInterface`: preservan la intención de conexión y registran los parámetros requeridos, pero no son modelos numéricos. La posición inicial selecciona BB-220-1 y deja abierta BB-220-2 para ambas posiciones. Si se cierran ambos selectores de barra de una posición, la validación detecta la doble selección y el caso se marca estructuralmente inválido.

**No es un diseño de subestación constructivo ni un expediente de ingeniería listo para emisión.** No se han inventado fabricante, corriente nominal, capacidad de corte, relación de transformación, potencia, grupo vectorial, impedancias, longitud, conductores, niveles BIL, TC/TP, protecciones, enclavamientos, puesta a tierra ni configuración de barra. El estudio numérico permanece bloqueado hasta resolver esos datos.

## 9. Limitaciones de esta auditoría

- La inspección es estática sobre el snapshot disponible, sin Git metadata y no es un perfil de rendimiento.
- El entorno de auditoría no tiene PySide6 ni Ruff instalados; por tanto, la interfaz Qt y los gates Ruff no se ejecutaron aquí.
- Se ejecutó la suite Python después del cambio local del código: 564 passed, 4 skipped. Esa ejecución no sustituye el gate Windows de la UI ni una validación eléctrica externa.
- No se verificó publicación, GitHub Pages, GitHub Releases ni compilación portable en Windows limpio.
