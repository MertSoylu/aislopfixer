/** The scales this page redefined. Arbitrary values carry the rest: the point
 *  of the case is that a page written entirely in escape hatches is still a
 *  page somebody made decisions on. */
module.exports = {
  content: ['./index.html'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Söhne', 'system-ui', 'sans-serif'],
        serif: ['Lyon', 'Georgia', 'serif'],
      },
    },
  },
};
