const API = "https://ratelock.onrender.com";

const token = prompt("Enter admin JWT token");

async function loadUsers(){

const res = await fetch(API + "/admin/users",{

headers:{
"Authorization":"Bearer " + token
}

});

const users = await res.json();

const container = document.getElementById("users");

container.innerHTML = "";

users.forEach(user=>{

const div = document.createElement("div");

div.className = "info-card";

div.innerHTML = `
<p><b>Email:</b> ${user.email}</p>
<p><b>Approved:</b> ${user.is_approved}</p>
<button onclick="approveUser(${user.id})">Approve</button>
`;

container.appendChild(div);

});

}

async function approveUser(id){

await fetch(API + "/admin/approve/" + id,{

method:"POST",

headers:{
"Authorization":"Bearer " + token
}

});

alert("User approved");

loadUsers();

}