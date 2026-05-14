const token = localStorage.getItem("token");
if (!token) window.location.href = "login.html";

const payload = JSON.parse(atob(token.split(".")[1]));
const role = payload.role;
const username = payload.sub;

function el(id) {
  return document.getElementById(id);
}

if (el("welcomeMsg")) {
  el("welcomeMsg").innerText = `Welcome, ${username} (${role})`;
}

if (role === "admin" && el("createExamLink")) {
  el("createExamLink").style.display = "inline";
}

// ✅ Create Exam (admin only) — handles createExamForm in create-exam.html
const createExamForm = el("createExamForm");
if (createExamForm) {
  createExamForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const msgEl = el("message");

    const body = {
      title: el("title").value.trim(),
      description: el("description").value.trim(),
      duration_minutes: parseInt(el("duration").value)
    };

    try {
      const response = await fetch(`${API_BASE_URL}/exams`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (response.ok) {
        msgEl.style.color = "green";
        msgEl.textContent = `✅ Exam "${data.exam.title}" created successfully!`;
        createExamForm.reset();
        setTimeout(() => window.location.href = "exams.html", 1500);
      } else {
        msgEl.style.color = "red";
        msgEl.textContent = data.detail || "Failed to create exam.";
      }
    } catch (error) {
      console.error("createExam ERROR:", error);
      msgEl.style.color = "red";
      msgEl.textContent = "Server error. Please try again.";
    }
  });
}

// ✅ Load Exams — backend returns {source, data: [...]}
async function loadExams() {
  const examsList = el("examsList");
  if (!examsList) return;

  try {
    const response = await fetch(`${API_BASE_URL}/exams`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    const res = await response.json();

    // backend wraps exams in {source, data: [...]}
    const exams = Array.isArray(res) ? res
      : Array.isArray(res.data) ? res.data
      : Array.isArray(res.exams) ? res.exams
      : [];

    examsList.innerHTML = "";

    if (exams.length === 0) {
      examsList.innerHTML = "<p>No exams available.</p>";
      return;
    }

    exams.forEach(exam => {
      const div = document.createElement("div");
      div.className = "exam-card";
      div.innerHTML = `
        <h3>${exam.title || "Exam"}</h3>
        <p>${exam.description || "No description"}</p>
        <p>Duration: ${exam.duration_minutes || 0} mins</p>
        <button onclick="startExam(${exam.id}, '${exam.title.replace(/'/g, "\\'")}')">Start Exam</button>
        ${role === "admin" ? `<button onclick="deleteExam(${exam.id})">Delete</button>` : ""}
      `;
      examsList.appendChild(div);
    });

  } catch (error) {
    console.error("loadExams ERROR:", error);
    if (el("message")) el("message").textContent = "Failed to load exams.";
  }
}

// ✅ Start Exam — students use /student/exams/{id}/questions, admins use /exams/{id}/questions
async function startExam(examId, examTitle) {
  try {
    // Admin must first start exam attempt if student, here admin can preview
    // Students must start attempt first, then load questions
    let questionsData;

    if (role === "student") {
      // Step 1: start attempt
      const startRes = await fetch(`${API_BASE_URL}/student/exams/start`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ exam_id: examId })
      });
      if (!startRes.ok) {
        const err = await startRes.json();
        if (el("message")) el("message").textContent = err.detail || "Could not start exam.";
        return;
      }

      // Step 2: load questions (student endpoint — no correct_answer exposed)
      const qRes = await fetch(`${API_BASE_URL}/student/exams/${examId}/questions`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const qData = await qRes.json();
      // backend wraps in {source, data: {exam_id, questions}}
      questionsData = qData.data ? qData.data : qData;

    } else {
      // Admin: load questions with answers visible
      const qRes = await fetch(`${API_BASE_URL}/exams/${examId}/questions`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const qData = await qRes.json();
      questionsData = qData.data ? qData.data : qData;
    }

    const questions = questionsData.questions || [];

    el("examTitle").innerText = examTitle;
    const questionsList = el("questionsList");
    questionsList.innerHTML = "";

    questions.forEach((q, index) => {
      const div = document.createElement("div");
      const choices = q.choices || [];

      let choicesHTML = "";
      if (q.question_type === "true_false") {
        choicesHTML = `
          <label><input type="radio" name="q${q.id}" value="true" required> True</label><br>
          <label><input type="radio" name="q${q.id}" value="false"> False</label><br>
        `;
      } else if (choices.length > 0) {
        choicesHTML = choices.map(choice => `
          <label>
            <input type="radio" name="q${q.id}" value="${choice}" required>
            ${choice}
          </label><br>
        `).join("");
      } else {
        // short answer
        choicesHTML = `<input type="text" id="sa_${q.id}" placeholder="Your answer..." style="width:100%;padding:6px;margin-top:4px">`;
      }

      // For admin: show correct answer
      const adminHint = (role === "admin" && q.correct_answer)
        ? `<small style="color:green">✔ Correct: ${q.correct_answer}</small><br>`
        : "";

      div.innerHTML = `
        <p><strong>${index + 1}. ${q.question_text}</strong></p>
        ${choicesHTML}
        ${adminHint}
        <br>
      `;
      questionsList.appendChild(div);
    });

    el("examForm").dataset.examId = examId;
    el("examForm").dataset.questions = JSON.stringify(questions.map(q => ({
      id: q.id,
      type: q.question_type
    })));

    el("examsList").style.display = "none";
    el("questionsSection").style.display = "block";
    el("resultsSection").style.display = "none";
    if (el("message")) el("message").textContent = "";

  } catch (error) {
    console.error("startExam ERROR:", error);
    if (el("message")) el("message").textContent = "Failed to load exam questions.";
  }
}

// ✅ Submit Exam — uses /student/exams/submit
const examForm = el("examForm");
if (examForm) {
  examForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    const examId = parseInt(this.dataset.examId);
    const questionsMeta = JSON.parse(this.dataset.questions);

    const answers = questionsMeta.map(q => {
      let answer = "";
      if (q.type === "short_answer") {
        const inp = document.getElementById(`sa_${q.id}`);
        answer = inp ? inp.value.trim() : "";
      } else {
        const selected = document.querySelector(`input[name="q${q.id}"]:checked`);
        answer = selected ? selected.value : "";
      }
      return { question_id: q.id, answer };
    });

    try {
      const response = await fetch(`${API_BASE_URL}/student/exams/submit`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ exam_id: examId, answers })
      });

      const data = await response.json();

      if (response.ok) {
        el("questionsSection").style.display = "none";
        // backend returns result.total_score / max_score / percentage
        const r = data.result;
        el("message").style.color = "green";
        el("message").innerText =
          `✅ Score: ${r.total_score}/${r.max_score} (${r.percentage.toFixed(1)}%)`;
        loadResults();
      } else {
        el("message").style.color = "red";
        el("message").innerText = data.detail || "Submission failed";
      }
    } catch (error) {
      console.error("submitExam ERROR:", error);
      el("message").style.color = "red";
      el("message").textContent = "Server error during submission.";
    }
  });
}

// ✅ Load Results
// Admin: GET /results  → {results: [{attempt_id, student_id, exam_id, total_score, max_score, percentage}]}
// Student: GET /student/exams/{exam_id}/result → per-exam, so we load all exams first
async function loadResults() {
  const resultsList = el("resultsList");
  if (!resultsList) return;

  try {
    resultsList.innerHTML = "<p>Loading results...</p>";

    if (role === "admin") {
      const response = await fetch(`${API_BASE_URL}/results`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await response.json();
      const results = data.results || [];

      resultsList.innerHTML = "";
      if (results.length === 0) {
        resultsList.innerHTML = "<p>No results yet.</p>";
      } else {
        results.forEach(r => {
          const div = document.createElement("div");
          div.className = "exam-card";
          div.innerHTML = `
            <h3>Exam #${r.exam_id}</h3>
            <p>Student ID: ${r.student_id}</p>
            <p>Score: ${r.total_score}/${r.max_score} (${Number(r.percentage).toFixed(1)}%)</p>
          `;
          resultsList.appendChild(div);
        });
      }

    } else {
      // Student: load exams first, then fetch result per exam
      const examsRes = await fetch(`${API_BASE_URL}/exams`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const examsData = await examsRes.json();
      const exams = Array.isArray(examsData.data) ? examsData.data
        : Array.isArray(examsData) ? examsData : [];

      resultsList.innerHTML = "";
      let hasAny = false;

      for (const exam of exams) {
        try {
          const rRes = await fetch(`${API_BASE_URL}/student/exams/${exam.id}/result`, {
            headers: { "Authorization": `Bearer ${token}` }
          });
          if (!rRes.ok) continue;
          const r = await rRes.json();
          hasAny = true;
          const div = document.createElement("div");
          div.className = "exam-card";
          div.innerHTML = `
            <h3>${exam.title}</h3>
            <p>Score: ${r.total_score}/${r.max_score} (${Number(r.percentage).toFixed(1)}%)</p>
          `;
          resultsList.appendChild(div);
        } catch (_) {}
      }

      if (!hasAny) {
        resultsList.innerHTML = "<p>No results yet.</p>";
      }
    }

    el("resultsSection").style.display = "block";
    el("examsList").style.display = "none";

  } catch (error) {
    console.error("loadResults ERROR:", error);
  }
}

// ✅ Delete Exam
async function deleteExam(examId) {
  if (!confirm("Are you sure you want to delete this exam?")) return;

  try {
    const response = await fetch(`${API_BASE_URL}/exams/${examId}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${token}` }
    });

    if (response.ok) {
      if (el("message")) el("message").innerText = "Exam deleted successfully";
      loadExams();
    } else {
      const data = await response.json();
      alert(data.detail || "Failed to delete exam");
    }
  } catch (error) {
    console.error("deleteExam ERROR:", error);
  }
}

// ✅ Logout
function logout() {
  localStorage.removeItem("token");
  window.location.href = "login.html";
}

// ✅ Init
loadExams();