# ND-012 — Transient CT and protection dynamics

## Scope

ND-012 adds a time-domain, single-phase CT equivalent, a sampled 50/51 numerical-relay
response model, and a three-pole ideal current-zero interruption estimate. It is an
engineering simulation layer; it is not a manufacturer firmware model, relay type test,
or declaration of IEC device-standard compliance.

## CT current waveform

The primary current is represented as a symmetrical sinusoidal component plus an
engineer-specified exponentially decaying DC component:

\[
i_p(t)=\sqrt{2}I_{p,\mathrm{rms}}\left[\sin(\omega t+\theta)
+d_0e^{-t/\tau_{dc}}\right].
\]

The ideal secondary current is \(i'_p=i_p/CTR\). The signed value \(d_0\) is the
initial DC component relative to the symmetrical AC peak; \(\theta\) is the fault
inception angle, and \(\tau_{dc}\) is supplied by the study engineer.

## CT nonlinear equivalent

The magnetizing branch is represented by a single-valued function
\(i_{exc}=g(\lambda)\), where \(\lambda\) is core flux linkage. Excitation test points
\((V_{rms},I_{exc,rms})\) are converted at the CT rated frequency:

\[
\lambda_j=\frac{\sqrt{2}V_j}{2\pi f_{rated}},\qquad
I_{exc,peak,j}=\sqrt{2}I_{exc,rms,j}.
\]

The curve is log-log interpolated between supplied points. Below the first point, a
linear segment through the origin is used. The final segment is continued numerically
only to complete integration; if a reported sample exceeds the supplied curve domain,
the result is marked `NOT_EVALUATED` and must not be interpreted as a validated
saturation prediction.

The CT secondary burden is modeled as a series resistance and inductance:

\[
R_\Sigma=R_{winding}+\Re(Z_b),\qquad
L_\Sigma=\frac{\Im(Z_b)}{2\pi f_{rated}}.
\]

With \(i_s=i'_p-g(\lambda)\), the flux-linkage equation is

\[
\frac{d\lambda}{dt}=R_\Sigma i_s+L_\Sigma\frac{di_s}{dt},
\]

or, after substituting \(di_s/dt=di'_p/dt-g'(\lambda)d\lambda/dt\),

\[
\boxed{\frac{d\lambda}{dt}=
\frac{R_\Sigma[i'_p-g(\lambda)]+L_\Sigma\,di'_p/dt}
{1+L_\Sigma g'(\lambda)}}.
\]

The ODE is integrated with SciPy RK45 and the engineer's maximum output time step.
The initial flux linkage is set by the signed remanence input in per unit of the
knee-point flux linkage.

## CT status and outputs

- `PASS`: no sample reaches the knee-point flux threshold and the supplied excitation
  curve covers the simulated flux range.
- `FAIL`: one or more samples reach or exceed knee-point flux; this flags a CT saturation
  condition in the single-valued model, not a failed physical test certificate.
- `NOT_EVALUATED`: flux exceeds the supplied excitation curve range or the numerical
  integration cannot support an engineering interpretation.

Samples include primary current, ideal secondary current, exciting current, loaded
secondary current and voltage, flux linkage, flux per unit of knee flux, and a saturation
flag. Aggregate metrics include saturation fraction and RMS current-transfer error.

## 50/51 numerical response

The relay evaluator consumes instantaneous secondary-side current samples. It requires
uniform time spacing and at least 32 samples per power-frequency cycle. A sliding RMS
window is formed over the configured number of cycles (one cycle by default).

For an inverse-time element, the normalized timer accumulates as

\[
u_{n+1}=u_n+\frac{\Delta t}{t_{op}(I_{rms,n})},
\]

where \(t_{op}\) is the existing IEC inverse-time characteristic in `OvercurrentRelay`.
The timer trips at \(u\ge1\). Below the configured dropout ratio, the timer decays
exponentially with the engineer-supplied reset time constant; between dropout and
pickup it holds. The 50 element accumulates its configured definite delay while the
RMS measurement exceeds its instantaneous pickup. Relay output delay is added after
the trip command.

This is a transparent numerical approximation. It does not model relay analog filters,
DFT implementation, frequency tracking, internal sampling jitter, manufacturer reset
curves, contact output tolerances, or firmware-specific logic.

## Circuit-breaker interruption estimate

The breaker evaluator starts contact separation after the relay output time plus the
breaker opening time and per-pole scatter. For each phase, it linearly interpolates the
current waveform and identifies the first subsequent natural current zero inside the
configured arc window. Overall clearing time is measured from relay trip command to
latest pole current zero.

This is an ideal current-zero estimate only. It does not model arc conductance, TRV,
dielectric recovery, chopping, restrike, pole grading capacitors, or actual interruption
capability tests. `NOT_EVALUATED` is returned where the waveform does not cover a pole's
contact separation or subsequent current zero.

## Required inputs

- CT ratio, winding resistance, burden impedance, rated frequency, knee voltage and
  manufacturer excitation curve.
- Fault current RMS, system frequency, inception angle, DC offset, DC time constant,
  remanent flux, simulation duration and time step.
- Existing 50/51 relay settings plus relay RMS window, dropout ratio, reset time constant
  and output delay.
- Three-phase current waveforms, breaker opening time, pole scatter and arc window.

No generic CT excitation curve, X/R-derived DC time constant, relay reset curve or
breaker interruption capability is invented by the software.
