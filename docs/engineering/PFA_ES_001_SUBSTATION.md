# PFA-ES-001 — Subestación 220 kV de doble barra

## Objetivo

Vertical slice de ingeniería para crear, inspeccionar, validar y persistir un modelo de subestación 220 kV de doble barra, con una posición de línea y una posición de transformador. El modelo usa equipos, terminales y conexiones explícitos; el dibujo unifilar es una vista separada y enlazada mediante IDs de dominio y mapeos explícitos de terminales QET.

## Topología inicial

- Barras: `BB-220-1`, `BB-220-2`, ambas a 220 kV línea-línea.
- Posición línea `L-220-01` y posición transformador `TR-220-01`.
- Cada posición tiene: seccionador de barra 1 (CLOSED), seccionador de barra 2 (OPEN), interruptor (CLOSED) y seccionador lado equipo (CLOSED).
- Hay tres nodos internos por posición (selector de barra, nodo a través del interruptor y nodo de salida a equipo), seis en total; la selección de barra 1 o barra 2 se representa mediante la posición de los seccionadores selectores.
- Equipos de maniobra: ocho objetos de dominio `SwitchingDevice`, dos terminales cada uno.
- Fronteras externas: una línea y un transformador representados como `UnresolvedEquipmentInterface` de un terminal conectado al lado patio.
- Documento: diez símbolos QET con `equipment_id` y mapeos de pin gráfico a terminal de dominio; las coordenadas no participan en el cálculo.

## Conteos del modelo

| Objeto | Cantidad |
|---|---:|
| Barras (incluye nodos internos tipados) | 8 |
| `BUSBAR` | 2 |
| `CONNECTION_NODE` | 6 |
| Equipos de maniobra | 8 |
| Interfaces externas sin parámetros | 2 |
| Conexiones terminal–nodo | 18 |
| Símbolos del diagrama | 10 |

## Reglas topológicas

1. Todo terminal de equipo debe tener una conexión explícita.
2. Un seccionador/interruptor `CLOSED` conecta idealmente sus terminales mediante proyección de topología; no se estampa una impedancia casi cero.
3. Un dispositivo `OPEN` interrumpe esa continuidad.
4. Una posición no puede conectar simultáneamente su selector de barra 1 y de barra 2. El validador detecta una doble selección y rechaza el modelo estructural.
5. El estado gráfico del símbolo está asociado a la posición de dominio; cambiar un interruptor utiliza `SetSwitchPosition` y la pila undo/redo.
6. Cruces de líneas y solapamientos no crean conectividad.
7. Un mapeo de pin QET no crea equipos ni conexiones; solo referencia un equipo y terminal ya existentes.

## Procedencia de símbolos

El catálogo actual usa activos de QElectroTech fijados a un commit de origen y con hashes. El manifiesto etiqueta los símbolos como `candidate`. La ruta del fichero bajo `en_60617` no demuestra verificación contra IEC 60617 ni autoriza a afirmar conformidad. No utilizar estos recursos como dataset para entrenar IA: `ELEMENTS.LICENSE` contiene una prohibición expresa para esa finalidad.

## Datos necesarios para habilitar estudios

### Línea L-220-01

- Tensión nominal remota y nivel de tensión real.
- Longitud y modelo (serie / π).
- R1/X1, R2/X2, R0/X0 por unidad de longitud y unidad declarada.
- Frecuencia.
- Datos de conductor, cable, geometría/retorno y compensación shunt cuando proceda.
- Conexión y parámetros de extremo remoto; red equivalente o modelo de barras externas.

### Transformador TR-220-01

- Potencia nominal MVA.
- Tensiones nominales HV/LV.
- Conexiones de devanados, grupo vectorial/clock.
- Impedancias de secuencia y base de ensayo (MVA/kV), pérdidas y relación X/R si corresponde.
- Puesta a tierra/neutro de ambos lados.
- Tap changer, rango, paso, posición, tipo de regulación y estado.
- Datos de secuencia cero según conexión y construcción.

### Equipos de patio y barra

- Corrientes nominales y de cortocircuito, tiempo de despeje, capacidad de cierre/corte, niveles de aislamiento, BIL, corriente térmica/dinámica, TC/TP, medida/protección y enclavamientos según el objetivo del estudio.
- Identificación de fabricante/modelo y referencias de datasheet/documento.
- Estados operativos y normal-open/normal-closed documentados.

Los campos requeridos del interfaz se conservan como `UNRESOLVED`; un dato con valor debe acompañarse de evidencia (`SOURCE_VERIFIED`, `USER_CONFIRMED` o `DERIVED`) y `source_reference`. No se acepta `bool`, NaN ni infinito como parámetro numérico. Si existen fuentes incompatibles, el estado debe ser `CONFLICTING` y el cálculo permanecer bloqueado.

## Flujo de la aplicación

`BuildPFAES001Substation` → `NetworkWorkspace` + `Network` aggregate → `WorkbenchWindow` y `NetworkCanvasView` → inspector de equipo → `SetSwitchPosition` → `Network.replace_equipment` → `JSONNetworkDocumentRepository` schema 1.2.

El builder crea el modelo, no ejecuta un estudio. `RunNetworkShortCircuitStudy` consume las redes de secuencia existentes, pero `SequenceNetworkBuilder` produce el diagnóstico `SEQ-EQUIPMENT-MODEL-UNRESOLVED` para las interfaces y el caso no se puede calcular hasta que se proporcionen modelos físicos completos.

## Criterios de aceptación locales

- Construcción crea 8 barras/nodos, 10 equipos, 18 conexiones y 10 símbolos.
- Dos barras se identifican como `BUSBAR`, seis nodos como `CONNECTION_NODE`.
- Cada posición tiene selección BB1 cerrada y BB2 abierta.
- Todos los pines QET mapeados referencian un terminal de dominio conectado.
- La validación estructural pasa, pero `study_ready=False`.
- Cerrar simultáneamente ambos selectores de barra invalida el bay.
- Undo/redo de cambio de interruptor actualiza el objeto de dominio y la etiqueta de estado.
- Round-trip JSON schema 1.2 conserva equipos, estados y mapeos.
- Schema 1.0/1.1 sigue siendo legible; no se pierde el comportamiento de documentos existentes.
- El intento de cortocircuito se bloquea con diagnóstico de modelo no resuelto, no con datos inventados.

## Limitaciones explícitas de este primer slice

- Los seis nodos internos siguen implementados como `Bus` con `BusKind.CONNECTION_NODE`; la migración a una entidad `ConnectivityNode` independiente es una deuda arquitectónica abierta.
- La paleta no tiene todavía catálogo completo con inserción genérica de equipo; este slice se carga mediante un comando de plantilla de ingeniería.
- El inspector expone parámetros no resueltos y permite editar la posición de maniobra, pero no incluye aún un editor genérico de datos de placa/impedancias con validación de procedencia.
- El símbolo QET de línea/transformador es una referencia candidata mapeada al terminal de frontera; no representa todos los terminales físicos, fases, medidas ni equipo interno.
- No incorpora bahías completas con TC, TP, descargadores, seccionadores de tierra, protecciones, medición, telecomunicaciones, enclavamientos ni esquemas de control.
- No debe usarse como plano constructivo, estudio de coordinación o cálculo de cortocircuito real.
