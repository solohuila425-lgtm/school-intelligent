/**
 * Lista las aulas reales de la organización del usuario (GET /classrooms)
 * y permite entrar a una — esto es lo que faltaba para que el roomId de
 * la pizarra CRDT dejara de estar hardcodeado a "aula-demo". Un profesor
 * también puede crear una aula nueva e iniciar la clase en vivo desde acá.
 *
 * No compilado/ejecutado en este entorno (mismo motivo que el resto del
 * frontend: requiere navegador real). Sí se probó, en cambio, que el
 * backend responde correctamente a estos mismos endpoints (ver
 * core-erp-backend/tests/test_erp.py).
 */
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

interface ClassroomSummary {
  id: string;
  name: string;
  is_live: boolean;
  teacher_id: string;
}

export function ClassroomListPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [classrooms, setClassrooms] = useState<ClassroomSummary[]>([]);
  const [newClassroomName, setNewClassroomName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isTeacher = user?.role === "teacher" || user?.role === "admin";

  async function loadClassrooms() {
    if (!user) return;
    try {
      const res = await fetch(`${API_BASE_URL}/classrooms`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (!res.ok) throw new Error("No se pudieron cargar las aulas");
      setClassrooms(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    }
  }

  useEffect(() => {
    loadClassrooms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function handleCreateClassroom(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !newClassroomName.trim()) return;
    try {
      const res = await fetch(`${API_BASE_URL}/classrooms`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${user.token}` },
        body: JSON.stringify({ name: newClassroomName }),
      });
      if (!res.ok) throw new Error("No se pudo crear el aula");
      setNewClassroomName("");
      await loadClassrooms();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    }
  }

  async function handleEnterClassroom(classroomId: string) {
    // Si es profesor, inicia la clase en vivo (is_live=true) antes de
    // entrar — así el estado del ERP y el estado real de la pizarra
    // quedan sincronizados, en vez de que "is_live" sea decorativo.
    if (isTeacher && user) {
      await fetch(`${API_BASE_URL}/classrooms/${classroomId}/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      }).catch(() => {
        // Si falla (ej. no es el profesor dueño del aula), igual navegamos:
        // la pizarra funciona en modo observación aunque is_live no se marque.
      });
    }
    navigate(`/aula/${classroomId}`);
  }

  return (
    <div className="classroom-list">
      <header>
        <h2>Mis aulas</h2>
        <button onClick={() => logout(API_BASE_URL)}>Cerrar sesión</button>
      </header>

      {error && <p className="error">{error}</p>}

      <ul>
        {classrooms.map((c) => (
          <li key={c.id}>
            <span>{c.name}</span>
            {c.is_live && <span className="live-badge">🔴 EN VIVO</span>}
            <button onClick={() => handleEnterClassroom(c.id)}>
              {isTeacher ? "Iniciar / Entrar" : "Entrar"}
            </button>
          </li>
        ))}
        {classrooms.length === 0 && <p>No hay aulas todavía.</p>}
      </ul>

      {isTeacher && (
        <form onSubmit={handleCreateClassroom} className="create-classroom-form">
          <input
            type="text"
            placeholder="Nombre del aula nueva"
            value={newClassroomName}
            onChange={(e) => setNewClassroomName(e.target.value)}
          />
          <button type="submit">Crear aula</button>
        </form>
      )}
    </div>
  );
}
