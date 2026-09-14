// Alpine.js 数据与逻辑
function themeSwitcher() {
    return {
        theme: 'light', // 默认主题
        // 初始化：从本地存储或系统偏好获取主题
        init() {
            const saved = localStorage.getItem('theme');
            const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (saved) {
                this.theme = saved;
            } else if (systemPrefersDark) {
                this.theme = 'dark';
            }
            // 观察theme变化并保存到本地存储
            this.$watch('theme', (value) => {
                localStorage.setItem('theme', value);
            });
        },
        // 计算属性：根据theme返回对应的图标类
        get iconClass() {
            return this.theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        },
        // 切换主题的方法
        toggleTheme() {
            this.theme = this.theme === 'dark' ? 'light' : 'dark';
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
  const tabItems = document.querySelectorAll('.tabs li');
  
  tabItems.forEach(tab => {
    tab.addEventListener('click', function(e) {
      e.preventDefault(); // Stop the default anchor behavior
      
      // Remove 'is-active' from all tabs and panes
      document.querySelectorAll('.tabs li').forEach(item => {
        item.classList.remove('is-active');
      });
      document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('is-active');
      });
      
      // Add 'is-active' to clicked tab and corresponding pane
      this.classList.add('is-active');
      const targetId = this.getAttribute('data-target');
      document.getElementById(targetId).classList.add('is-active');
    });
  });
});