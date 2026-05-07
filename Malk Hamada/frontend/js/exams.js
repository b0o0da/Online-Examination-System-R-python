const examsList = document.getElementById("examsList");
const createExamForm = document.getElementById("createExamForm");
const message = document.getElementById("message");

if (!getToken()) {
  window.location.href = "login.html";
}

async function loadExams() {
  message.textContent = "";

  try {
    const response = await fetch(`${API_BASE_URL}/exams`, {
      method: "GET",
      headers: getAuthHeaders()
    });

    const data = await response.json();
    console.log("DATA:", data);

    const exams = Array.isArray(data) ? data : (data.exams || []);

    examsList.innerHTML = "";

    if (exams.length === 0) {
      examsList.innerHTML = "<p>No exams available.</p>";
      return;
    }

    exams.forEach(exam => {
      const examCard = document.createElement("div");
      examCard.className = "card";

      examCard.innerHTML = `
        <h3>${exam.title || "Exam"}</h3>
        <p>${exam.description || "No description"}</p>
        <p><strong>Duration:</strong> ${exam.duration_minutes || exam.duration || 0} minutes</p>
      `;

      examsList.appendChild(examCard);
    });

  } catch (error) {
    console.log("ERROR:", error);
   message.textContent = "No exams available.";
  }
}
  
async function deleteExam(examId) {
  const confirmDelete = confirm("Are you sure you want to delete this exam?");

  if (!confirmDelete) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/exams/${examId}`, {
      method: "DELETE",
      headers: getAuthHeaders()
    });

    if (!response.ok) {
      const data = await response.json();
      alert(data.detail || "Failed to delete exam");
      return;
    }

    alert("Exam deleted successfully");
    loadExams();

  } catch (error) {
    console.log("ERROR:", error);
    alert("Server error. Please try again.");
  }
}

loadExams();
