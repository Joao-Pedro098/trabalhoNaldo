"""Distância de pontos às falhas medida SOBRE A ESFERA (vale para qualquer escala).

Antes, as distâncias eram medidas num plano (projeção azimutal equidistante centrada na
área). Isso é ótimo para uma região, mas erra muito em escala continental ou mundial
(+4% no Brasil inteiro, +180% no mundo). Aqui tudo é feito em 3D na esfera:

1. Cada falha é "densificada" ao longo do grande círculo (um vértice a cada ~1 km) e os
   vértices viram vetores unitários 3D, indexados numa KD-tree (scipy.cKDTree).
2. Para cada ponto, os k vértices mais próximos dão os segmentos candidatos.
3. A distância exata ponto–arco de grande círculo é calculada para esses segmentos e
   fica a menor. Funciona igual nos polos e na longitude 180°.

Raio da esfera: raio médio da Terra (6.371,0088 km). A diferença para o elipsoide WGS84 é
de no máximo ~0,5%, muito menor que a incerteza de localização dos epicentros.
"""
from typing import Dict, List, Sequence, Tuple

import numpy as np
from scipy.spatial import cKDTree

RAIO_KM = 6371.0088
PASSO_KM = 1.0       # espaçamento máximo entre vértices densificados
K_CANDIDATOS = 8     # vértices vizinhos examinados por ponto


def para_xyz(lon, lat) -> np.ndarray:
    lon_r, lat_r = np.radians(np.asarray(lon, dtype=float)), np.radians(np.asarray(lat, dtype=float))
    c = np.cos(lat_r)
    return np.column_stack([c * np.cos(lon_r), c * np.sin(lon_r), np.sin(lat_r)])


def para_lonlat(xyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    xyz = xyz / np.linalg.norm(xyz, axis=1, keepdims=True)
    lon = np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0]))
    lat = np.degrees(np.arcsin(np.clip(xyz[:, 2], -1, 1)))
    return lon, lat


def _angulo(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Ângulo (rad) entre vetores unitários, estável para ângulos pequenos."""
    return np.arctan2(np.linalg.norm(np.cross(u, v), axis=-1), np.einsum("ij,ij->i", u, v))


def distancia_haversine_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    return RAIO_KM * _angulo(para_xyz(lon1, lat1), para_xyz(lon2, lat2))


def _partes(geometria: Dict) -> List:
    return [geometria["coordinates"]] if geometria["type"] == "LineString" else list(geometria["coordinates"])


def ponto_arco(P: np.ndarray, A: np.ndarray, B: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Distância angular (rad) de P ao arco de grande círculo AB e o ponto mais próximo nele."""
    n = np.cross(A, B)
    nn = np.linalg.norm(n, axis=1)
    degenerado = nn < 1e-15
    n_hat = n / np.where(degenerado, 1.0, nn)[:, None]
    s = np.einsum("ij,ij->i", P, n_hat)
    C = P - s[:, None] * n_hat
    cn = np.linalg.norm(C, axis=1)
    C = C / np.where(cn < 1e-15, 1.0, cn)[:, None]
    # C está dentro do arco se fica "entre" A e B no sentido de A -> B
    dentro = ((np.einsum("ij,ij->i", np.cross(A, C), n_hat) >= 0)
              & (np.einsum("ij,ij->i", np.cross(C, B), n_hat) >= 0) & ~degenerado & (cn >= 1e-15))
    d_meio = np.arcsin(np.clip(np.abs(s), 0, 1))
    d_a, d_b = _angulo(P, A), _angulo(P, B)
    usa_a = d_a <= d_b
    d_ponta = np.where(usa_a, d_a, d_b)
    ponta = np.where(usa_a[:, None], A, B)
    dist = np.where(dentro, d_meio, d_ponta)
    perto = np.where(dentro[:, None], C, ponta)
    return dist, perto


class IndiceGeodesico:
    """Falhas densificadas na esfera + KD-tree 3D."""

    def __init__(self, falhas: Sequence[Dict], passo_km: float = PASSO_KM):
        vertices, dono_v, parte_v = [], [], []
        self.comprimento_km: Dict = {}
        n_parte = 0
        for falha in falhas:
            for parte in _partes(falha["geometria"]):
                arr = np.asarray(parte, dtype=float)[:, :2]
                if len(arr) < 2:
                    continue
                xyz = para_xyz(arr[:, 0], arr[:, 1])
                A, B = xyz[:-1], xyz[1:]
                theta = _angulo(A, B)
                self.comprimento_km[falha["id"]] = self.comprimento_km.get(falha["id"], 0.0) + float(theta.sum()) * RAIO_KM
                passos = np.maximum(1, np.ceil(theta * RAIO_KM / passo_km).astype(int))
                # Interpolação esférica (slerp) em cada segmento
                seg = np.repeat(np.arange(len(A)), passos)
                t = np.concatenate([np.arange(p) / p for p in passos])
                th = theta[seg]
                sen = np.sin(th)
                linear = sen < 1e-12
                w_a = np.where(linear, 1 - t, np.sin((1 - t) * th) / np.where(linear, 1, sen))
                w_b = np.where(linear, t, np.sin(t * th) / np.where(linear, 1, sen))
                pts = w_a[:, None] * A[seg] + w_b[:, None] * B[seg]
                pts = np.vstack([pts, xyz[-1:]])
                pts /= np.linalg.norm(pts, axis=1, keepdims=True)
                vertices.append(pts)
                dono_v.append(np.full(len(pts), falha["id"], dtype=object))
                parte_v.append(np.full(len(pts), n_parte))
                n_parte += 1
        if not vertices:
            raise ValueError("Nenhuma falha com geometria válida.")
        self.v = np.vstack(vertices)
        self.dono = np.concatenate(dono_v)
        parte = np.concatenate(parte_v)
        # vértice i tem segmento (i, i+1) se o próximo é da mesma parte
        self.tem_proximo = np.append(parte[1:] == parte[:-1], False)
        self.tem_anterior = np.insert(parte[1:] == parte[:-1], 0, False)
        self.arvore = cKDTree(self.v)
        self.n_vertices = len(self.v)

    def mais_proxima(self, lon, lat, lote: int = 50_000):
        """(distância km, id da falha, lon e lat do ponto mais próximo na falha) para cada ponto."""
        P_todos = para_xyz(lon, lat)
        n = len(P_todos)
        dist = np.empty(n)
        dono = np.empty(n, dtype=object)
        perto = np.empty((n, 3))
        k = min(K_CANDIDATOS, self.n_vertices)
        for ini in range(0, n, lote):
            P = P_todos[ini:ini + lote]
            _, idx = self.arvore.query(P, k=k)
            idx = idx.reshape(len(P), k)
            # Segmentos candidatos: (i-1, i) e (i, i+1) de cada vértice vizinho
            base = np.concatenate([idx, idx], axis=1)
            valido = np.concatenate([self.tem_proximo[idx], self.tem_anterior[idx]], axis=1)
            # Segmento inexistente (fim de linha) vira o próprio vértice (A = B: distância ao ponto)
            ia = np.where(valido, np.concatenate([idx, idx - 1], axis=1), base)
            ib = np.where(valido, np.concatenate([idx + 1, idx], axis=1), base)
            m = ia.shape[1]
            Prep = np.repeat(P, m, axis=0)
            d, c = ponto_arco(Prep, self.v[ia.ravel()], self.v[ib.ravel()])
            d = d.reshape(len(P), m)
            melhor = np.argmin(d, axis=1)
            linhas = np.arange(len(P))
            dist[ini:ini + lote] = d[linhas, melhor] * RAIO_KM
            dono[ini:ini + lote] = self.dono[ia[linhas, melhor]]
            perto[ini:ini + lote] = c.reshape(len(P), m, 3)[linhas, melhor]
        plon, plat = para_lonlat(perto)
        return dist, dono, plon, plat
