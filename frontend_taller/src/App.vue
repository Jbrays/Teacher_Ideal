<template>
  <router-view />
</template>

<script>
export default {};
</script>

<style>
html, body {
  margin: 0;
  padding: 0;
  background-color: theme('colors.background');
  color: theme('colors.on-background');
  font-family: 'Hanken Grotesk', sans-serif;
}
.material-symbols-outlined {
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}
.material-symbols-outlined.fill {
  font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}

/* Custom scrollbar for textareas */
textarea::-webkit-scrollbar {
  width: 6px;
}
textarea::-webkit-scrollbar-track {
  background: transparent;
}
textarea::-webkit-scrollbar-thumb {
  background-color: theme('colors.outline-variant');
  border-radius: 20px;
}
</style>
